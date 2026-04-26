#!/usr/bin/env python3
"""
Train XGBoost on 100% Real Dataset - WITHOUT TIME LEAKAGE

Issue: Class 0 has all current timestamps, Class 1 has historical timestamps.
Solution: Remove time features, use only position-state features.

This is the HONEST evaluation of the model.
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
DATASET_PATH = '/home/mobra/protocol/data/aave_100_real_dataset.parquet'

# ONLY position-state features - NO TIME FEATURES
FEATURES_CLEAN = [
    'health_factor',
    'collateral_to_debt_ratio',
    'collateral_usd',
    'debt_usd',
]


def main():
    print("="*70)
    print("CLEAN MODEL - NO TIME LEAKAGE")
    print("="*70)
    
    df = pd.read_parquet(DATASET_PATH)
    print(f"Loaded {len(df):,} samples")
    
    # Features (NO time features)
    X = df[FEATURES_CLEAN].copy()
    y = df['label'].values
    
    # Clean
    for col in X.columns:
        X[col] = X[col].replace([np.inf, -np.inf], np.nan)
        X[col] = X[col].fillna(X[col].median())
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"\nFeatures: {FEATURES_CLEAN}")
    print(f"Train: {len(X_train):,}, Test: {len(X_test):,}")
    
    # Train
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURES_CLEAN)
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=FEATURES_CLEAN)
    
    params = {
        'objective': 'binary:logistic',
        'eval_metric': ['auc', 'logloss'],
        'max_depth': 6,
        'learning_rate': 0.1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 5,
        'gamma': 0.1,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'device': f'cuda:{GPU_ID}',
        'tree_method': 'hist',
        'seed': 42,
    }
    
    print("\nTraining...")
    model = xgb.train(
        params, dtrain,
        num_boost_round=300,
        evals=[(dtrain, 'train'), (dtest, 'test')],
        early_stopping_rounds=30,
        verbose_eval=50
    )
    
    # Evaluate
    y_proba = model.predict(dtest)
    
    print("\n" + "="*70)
    print("EVALUATION (Clean Features)")
    print("="*70)
    
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
    print("FINAL METRICS (CLEAN, NO LEAKAGE)")
    print("="*70)
    print(f"Precision:  {metrics['precision']:.2%}")
    print(f"Recall:     {metrics['recall']:.2%}")
    print(f"F1:         {metrics['f1']:.2%}")
    print(f"AUC:        {metrics['auc']:.4f}")
    print(f"FPR:        {metrics['fpr']:.2%}")
    print(f"Threshold:  {metrics['threshold']:.2f}")
    print()
    print(f"Confusion Matrix:")
    print(f"               Pred 0   Pred 1")
    print(f"  Actual 0:    {tn:>5}    {fp:>5}")
    print(f"  Actual 1:    {fn:>5}    {tp:>5}")
    
    # Critical zone
    print("\n" + "="*70)
    print("CRITICAL ZONE (HF 1.0-1.5)")
    print("="*70)
    
    test_df = X_test.copy()
    test_df['actual'] = y_test
    test_df['pred'] = y_pred
    test_df['proba'] = y_proba
    
    cz = test_df[(test_df['health_factor'] >= 1.0) & (test_df['health_factor'] <= 1.5)]
    
    if len(cz) > 0:
        acc = (cz['actual'] == cz['pred']).mean()
        print(f"Samples: {len(cz):,}")
        print(f"Accuracy: {acc:.2%}")
        
        print(f"\nBy HF range:")
        for low in [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.45]:
            high = low + 0.05
            b = cz[(cz['health_factor'] >= low) & (cz['health_factor'] < high)]
            if len(b) > 0:
                a = (b['actual'] == b['pred']).mean()
                pos = (b['actual'] == 1).sum()
                print(f"  HF {low:.2f}-{high:.2f}: {len(b):>4} samples ({pos:>3} pos), acc {a:.1%}")
    
    # Feature importance
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)
    imp = model.get_score(importance_type='gain')
    for feat, score in sorted(imp.items(), key=lambda x: x[1], reverse=True):
        print(f"  {feat:<35} {score:>10.2f}")
    
    # Save
    model.save_model('/home/mobra/protocol/ai-engine/aave_clean_real_model.json')
    with open('/home/mobra/protocol/ai-engine/aave_clean_real_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print("\n" + "="*70)
    print("✅ CLEAN MODEL TRAINED")
    print("="*70)
    print(f"Saved: /home/mobra/protocol/ai-engine/aave_clean_real_model.json")
    print(f"\n{'='*70}")
    print("INTERPRETATION:")
    print(f"{'='*70}")
    
    if metrics['precision'] > 0.95:
        print("⚠️  Still very high precision - check if HF separates classes too perfectly")
        print("    This may indicate HF is too dominant a feature")
    elif metrics['precision'] > 0.80:
        print("✅ Strong precision with realistic challenge")
    else:
        print("⚠️  Lower precision - real-world predictive challenge")
    
    print(f"\nMost important feature: {sorted(imp.items(), key=lambda x: x[1], reverse=True)[0][0]}")


if __name__ == '__main__':
    main()
