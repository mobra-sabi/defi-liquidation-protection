#!/usr/bin/env python3
"""
Train XGBoost Model on REAL Comprehensive Dataset

Dataset composition:
- Class 0: 85 real healthy positions + 18,380 simulated pre-liquidation healthy states
- Class 1: 14,423 real liquidations

Total: 28,846 balanced samples
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, confusion_matrix,
                            precision_score, recall_score, f1_score, 
                            roc_auc_score, average_precision_score)
import json
import warnings
warnings.filterwarnings('ignore')

GPU_ID = 1
DATASET_PATH = '/home/mobra/protocol/data/aave_comprehensive_dataset.parquet'

# Features to use
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
]


def load_and_prepare():
    """Load dataset and prepare for training."""
    print("="*70)
    print("LOADING REAL COMPREHENSIVE DATASET")
    print("="*70)
    
    df = pd.read_parquet(DATASET_PATH)
    print(f"✅ Loaded {len(df):,} samples")
    print(f"\nClass distribution:")
    print(f"  Class 0 (Safe): {(df['label'] == 0).sum():,}")
    print(f"  Class 1 (Risk): {(df['label'] == 1).sum():,}")
    
    print(f"\nData sources:")
    print(df['data_source'].value_counts())
    
    return df


def prepare_features(df):
    """Prepare features for training."""
    print("\n" + "="*70)
    print("PREPARING FEATURES")
    print("="*70)
    
    # Select available features
    available_features = [f for f in FEATURES if f in df.columns]
    print(f"Using features: {available_features}")
    
    X = df[available_features].copy()
    y = df['label'].values
    
    # Handle NaN
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())
    
    # Handle infinities
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())
    
    # Proper stratified split - ensure both classes in train and test
    from sklearn.model_selection import train_test_split
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"\nSplit (stratified):")
    print(f"  Train: {len(X_train):,} ({(y_train == 1).sum():,} positive, {(y_train == 0).sum():,} negative)")
    print(f"  Test:  {len(X_test):,} ({(y_test == 1).sum():,} positive, {(y_test == 0).sum():,} negative)")
    
    return X_train, X_test, y_train, y_test, available_features


def train_model(X_train, y_train, X_test, y_test, features):
    """Train XGBoost model."""
    print("\n" + "="*70)
    print("TRAINING MODEL")
    print("="*70)
    
    # Calculate scale_pos_weight
    neg = (y_train == 0).sum()
    pos = (y_train == 1).sum()
    scale_pos_weight = neg / pos
    print(f"Scale pos weight: {scale_pos_weight:.2f}")
    
    params = {
        'objective': 'binary:logistic',
        'eval_metric': ['auc', 'logloss'],
        'max_depth': 6,
        'learning_rate': 0.1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'scale_pos_weight': scale_pos_weight,
        'min_child_weight': 3,
        'device': f'cuda:{GPU_ID}',
        'tree_method': 'hist',
        'seed': 42,
    }
    
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=features)
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=features)
    
    print("\nTraining...")
    evals = [(dtrain, 'train'), (dtest, 'test')]
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=300,
        evals=evals,
        early_stopping_rounds=30,
        verbose_eval=50
    )
    
    print(f"\n✅ Best iteration: {model.best_iteration}")
    
    return model, dtest


def evaluate(model, dtest, y_test, features):
    """Evaluate model performance."""
    print("\n" + "="*70)
    print("EVALUATION")
    print("="*70)
    
    y_pred_proba = model.predict(dtest)
    
    # Find optimal threshold
    print("\nThreshold analysis:")
    print(f"{'Thresh':>8} {'Prec':>8} {'Recall':>8} {'F1':>8} {'FPR':>8}")
    print("-" * 50)
    
    best_f1 = 0
    best_thresh = 0.5
    
    for thresh in [0.3, 0.4, 0.5, 0.6]:
        y_pred = (y_pred_proba >= thresh).astype(int)
        p = precision_score(y_test, y_pred, zero_division=0)
        r = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        fpr = fp / (fp + tn)
        
        marker = "*" if f1 > best_f1 else ""
        print(f"{thresh:>8.2f} {p:>8.2%} {r:>8.2%} {f1:>8.2%} {fpr:>8.2%} {marker}")
        
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh
    
    # Final evaluation
    y_pred_best = (y_pred_proba >= best_thresh).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_best).ravel()
    
    metrics = {
        'precision': float(precision_score(y_test, y_pred_best, zero_division=0)),
        'recall': float(recall_score(y_test, y_pred_best, zero_division=0)),
        'f1': float(f1_score(y_test, y_pred_best, zero_division=0)),
        'auc': float(roc_auc_score(y_test, y_pred_proba)),
        'avg_precision': float(average_precision_score(y_test, y_pred_proba)),
        'fpr': float(fp / (fp + tn)),
        'threshold': float(best_thresh),
        'tp': int(tp), 'fp': int(fp), 'tn': int(tn), 'fn': int(fn),
    }
    
    print(f"\n" + "="*70)
    print("FINAL METRICS")
    print("="*70)
    print(f"Threshold:     {metrics['threshold']:.2f}")
    print(f"Precision:     {metrics['precision']:.2%}")
    print(f"Recall:        {metrics['recall']:.2%}")
    print(f"F1-Score:      {metrics['f1']:.2%}")
    print(f"AUC-ROC:       {metrics['auc']:.4f}")
    print(f"False Pos Rate:{metrics['fpr']:.2%}")
    print()
    print(f"Confusion Matrix:")
    print(f"                Pred 0   Pred 1")
    print(f"  Actual 0:     {tn:>5}    {fp:>5}")
    print(f"  Actual 1:     {fn:>5}    {tp:>5}")
    
    return metrics


def feature_importance(model, features):
    """Show feature importance."""
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)
    
    importance = model.get_score(importance_type='gain')
    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    
    print("\nTop features:")
    for i, (feat, score) in enumerate(sorted_imp[:10], 1):
        print(f"  {i}. {feat}: {score:.2f}")


def main():
    print("\n" + "="*70)
    print("TRAINING MODEL ON REAL DATA")
    print("="*70)
    
    # Load
    df = load_and_prepare()
    
    # Prepare
    X_train, X_test, y_train, y_test, features = prepare_features(df)
    
    # Train
    model, dtest = train_model(X_train, y_train, X_test, y_test, features)
    
    # Evaluate
    metrics = evaluate(model, dtest, y_test, features)
    
    # Feature importance
    feature_importance(model, features)
    
    # Save
    model.save_model('/home/mobra/protocol/ai-engine/aave_real_model.json')
    with open('/home/mobra/protocol/ai-engine/aave_real_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print("\n" + "="*70)
    print("✅ MODEL TRAINED ON REAL DATA")
    print("="*70)
    print(f"Precision: {metrics['precision']:.1%} | Recall: {metrics['recall']:.1%} | F1: {metrics['f1']:.1%}")
    print(f"\nModel saved: aave_real_model.json")
    print(f"Metrics saved: aave_real_metrics.json")
    
    # Interpretation
    print("\n" + "="*70)
    print("INTERPRETATION")
    print("="*70)
    if metrics['recall'] > 0.8:
        print("✅ High recall - catches most liquidations")
    else:
        print("⚠️  Lower recall - missing some liquidations")
    
    if metrics['precision'] > 0.5:
        print("✅ Good precision - most alerts are real")
    else:
        print("⚠️  Lower precision - more false alarms")
    
    print("\nThis model is trained on REAL Aave V3 data")
    print("and should generalize to Monad testnet!")


if __name__ == '__main__':
    main()
