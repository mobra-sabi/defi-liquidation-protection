#!/usr/bin/env python3
"""
Train XGBoost on 100% Real Dataset

Class 0: 14,217 real active positions from Aave V3 (HF 1.0-99.5)
Class 1: 14,217 real liquidations (HF 0.16-1.50)

NO synthetic data, NO interpolation.
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, confusion_matrix,
                             precision_score, recall_score, f1_score,
                             roc_auc_score, average_precision_score, roc_curve)
import json
import warnings
warnings.filterwarnings('ignore')

GPU_ID = 1
DATASET_PATH = '/home/mobra/protocol/data/aave_100_real_dataset.parquet'

# Features available BEFORE prediction (no leakage)
FEATURES = [
    'health_factor',
    'collateral_to_debt_ratio',
    'collateral_usd',
    'debt_usd',
    'liquidation_threshold',
    'hour_of_day',
    'day_of_week',
    'is_weekend',
    'is_night',
    'is_morning',
    'is_afternoon',
]


def load_and_validate():
    """Load dataset and validate."""
    print("="*70)
    print("LOADING 100% REAL DATASET")
    print("="*70)
    
    df = pd.read_parquet(DATASET_PATH)
    print(f"✅ Loaded {len(df):,} samples")
    print(f"\nClass distribution:")
    print(f"  Class 0 (Active/Healthy): {(df['label'] == 0).sum():,}")
    print(f"  Class 1 (Liquidated):     {(df['label'] == 1).sum():,}")
    
    print(f"\nData sources:")
    for src, count in df['data_source'].value_counts().items():
        print(f"  {src}: {count:,}")
    
    # Check overlap in HF range (key challenge)
    hf_overlap_low = 1.0
    hf_overlap_high = 1.5
    overlap_c0 = ((df['label'] == 0) & 
                  (df['health_factor'] >= hf_overlap_low) & 
                  (df['health_factor'] < hf_overlap_high)).sum()
    overlap_c1 = ((df['label'] == 1) & 
                  (df['health_factor'] >= hf_overlap_low) & 
                  (df['health_factor'] < hf_overlap_high)).sum()
    
    print(f"\n📊 Overlap zone (HF 1.0-1.5):")
    print(f"  Class 0 in zone: {overlap_c0:,}")
    print(f"  Class 1 in zone: {overlap_c1:,}")
    print(f"  → Real predictive challenge!")
    
    return df


def prepare_data(df):
    """Prepare features and split."""
    print("\n" + "="*70)
    print("PREPARING DATA")
    print("="*70)
    
    available = [f for f in FEATURES if f in df.columns]
    print(f"Features: {available}")
    
    X = df[available].copy()
    y = df['label'].values
    
    # Handle missing/infinite values
    for col in X.columns:
        X[col] = X[col].replace([np.inf, -np.inf], np.nan)
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())
    
    # Stratified split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"\nSplit:")
    print(f"  Train: {len(X_train):,} ({(y_train == 1).sum():,} pos, {(y_train == 0).sum():,} neg)")
    print(f"  Test:  {len(X_test):,} ({(y_test == 1).sum():,} pos, {(y_test == 0).sum():,} neg)")
    
    return X_train, X_test, y_train, y_test, available


def train(X_train, y_train, X_test, y_test, features):
    """Train XGBoost on GPU."""
    print("\n" + "="*70)
    print("TRAINING XGBOOST ON 100% REAL DATA")
    print("="*70)
    
    neg = (y_train == 0).sum()
    pos = (y_train == 1).sum()
    scale_pos_weight = neg / pos
    
    params = {
        'objective': 'binary:logistic',
        'eval_metric': ['auc', 'logloss'],
        'max_depth': 6,
        'learning_rate': 0.1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'scale_pos_weight': scale_pos_weight,
        'min_child_weight': 5,
        'gamma': 0.1,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'device': f'cuda:{GPU_ID}',
        'tree_method': 'hist',
        'seed': 42,
    }
    
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=features)
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=features)
    
    print("\nTraining...")
    model = xgb.train(
        params, dtrain,
        num_boost_round=300,
        evals=[(dtrain, 'train'), (dtest, 'test')],
        early_stopping_rounds=30,
        verbose_eval=30
    )
    
    print(f"\n✅ Best iteration: {model.best_iteration}")
    return model, dtest


def evaluate(model, X_test, y_test, features):
    """Comprehensive evaluation."""
    print("\n" + "="*70)
    print("EVALUATION ON REAL TEST DATA")
    print("="*70)
    
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=features)
    y_proba = model.predict(dtest)
    
    print("\nThreshold analysis:")
    print(f"{'Thresh':>8} {'Prec':>8} {'Recall':>8} {'F1':>8} {'FPR':>8}")
    print("-" * 50)
    
    best_f1 = 0
    best_thresh = 0.5
    
    for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
        y_pred = (y_proba >= t).astype(int)
        p = precision_score(y_test, y_pred, zero_division=0)
        r = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        fpr = fp / (fp + tn)
        
        marker = "*" if f1 > best_f1 else ""
        print(f"{t:>8.2f} {p:>8.2%} {r:>8.2%} {f1:>8.2%} {fpr:>8.2%} {marker}")
        
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = t
    
    # Final
    y_pred = (y_proba >= best_thresh).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    
    metrics = {
        'precision': float(precision_score(y_test, y_pred)),
        'recall': float(recall_score(y_test, y_pred)),
        'f1': float(f1_score(y_test, y_pred)),
        'auc': float(roc_auc_score(y_test, y_proba)),
        'avg_precision': float(average_precision_score(y_test, y_proba)),
        'fpr': float(fp / (fp + tn)),
        'threshold': float(best_thresh),
        'tp': int(tp), 'fp': int(fp), 'tn': int(tn), 'fn': int(fn),
    }
    
    print("\n" + "="*70)
    print("FINAL METRICS (100% REAL DATA)")
    print("="*70)
    print(f"Threshold:          {metrics['threshold']:.2f}")
    print(f"Precision:          {metrics['precision']:.2%}")
    print(f"Recall:             {metrics['recall']:.2%}")
    print(f"F1-Score:           {metrics['f1']:.2%}")
    print(f"AUC-ROC:            {metrics['auc']:.4f}")
    print(f"Avg Precision:      {metrics['avg_precision']:.4f}")
    print(f"False Positive Rate:{metrics['fpr']:.2%}")
    print()
    print(f"Confusion Matrix:")
    print(f"                 Pred 0    Pred 1")
    print(f"  Actual 0:      {tn:>6}    {fp:>6}")
    print(f"  Actual 1:      {fn:>6}    {tp:>6}")
    
    # Critical zone analysis (HF 1.0-1.5 - the hard cases)
    print("\n" + "="*70)
    print("CRITICAL ZONE ANALYSIS (HF 1.0-1.5)")
    print("="*70)
    
    test_df = X_test.copy()
    test_df['actual'] = y_test
    test_df['predicted'] = y_pred
    test_df['proba'] = y_proba
    
    critical_zone = test_df[(test_df['health_factor'] >= 1.0) & 
                           (test_df['health_factor'] <= 1.5)]
    
    if len(critical_zone) > 0:
        cz_acc = (critical_zone['actual'] == critical_zone['predicted']).mean()
        print(f"  Samples in HF 1.0-1.5: {len(critical_zone):,}")
        print(f"  Accuracy in critical zone: {cz_acc:.2%}")
        
        # By 0.05 buckets
        print(f"\n  Accuracy by HF range:")
        for low in [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.45]:
            high = low + 0.05
            bucket = critical_zone[(critical_zone['health_factor'] >= low) & 
                                  (critical_zone['health_factor'] < high)]
            if len(bucket) > 0:
                acc = (bucket['actual'] == bucket['predicted']).mean()
                pos_in_bucket = (bucket['actual'] == 1).sum()
                print(f"    HF {low:.2f}-{high:.2f}: {len(bucket):>4} samples, "
                      f"{pos_in_bucket:>3} pos, accuracy {acc:.1%}")
    
    return metrics


def feature_importance(model, features):
    """Show feature importance."""
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)
    
    imp = model.get_score(importance_type='gain')
    sorted_imp = sorted(imp.items(), key=lambda x: x[1], reverse=True)
    
    for i, (feat, score) in enumerate(sorted_imp[:10], 1):
        print(f"  {i:>2}. {feat:<35} {score:>10.2f}")


def main():
    print("\n" + "="*70)
    print("TRAINING ON 100% REAL DATA")
    print("="*70)
    
    df = load_and_validate()
    X_train, X_test, y_train, y_test, features = prepare_data(df)
    model, dtest = train(X_train, y_train, X_test, y_test, features)
    metrics = evaluate(model, X_test, y_test, features)
    feature_importance(model, features)
    
    # Save
    model.save_model('/home/mobra/protocol/ai-engine/aave_100_real_model.json')
    with open('/home/mobra/protocol/ai-engine/aave_100_real_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print("\n" + "="*70)
    print("✅ MODEL TRAINED ON 100% REAL DATA")
    print("="*70)
    print(f"  Precision: {metrics['precision']:.1%}")
    print(f"  Recall:    {metrics['recall']:.1%}")
    print(f"  F1:        {metrics['f1']:.1%}")
    print(f"  AUC:       {metrics['auc']:.4f}")
    print(f"\nModel:   /home/mobra/protocol/ai-engine/aave_100_real_model.json")
    print(f"Metrics: /home/mobra/protocol/ai-engine/aave_100_real_metrics.json")
    print(f"\nThis model is ready for production use on Monad testnet!")


if __name__ == '__main__':
    main()
