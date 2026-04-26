#!/usr/bin/env python3
"""
HF-Only Test - The Truth Test

If a model with ONLY health_factor achieves high accuracy,
then HF alone is sufficient (rule-based wins).

If HF-only is much worse than full model, the additional features add value.
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (precision_score, recall_score, f1_score,
                             roc_auc_score, confusion_matrix)
import warnings
warnings.filterwarnings('ignore')


def main():
    df = pd.read_parquet('/home/mobra/protocol/data/aave_100_real_dataset.parquet')
    
    print("="*70)
    print("TEST: HF-ONLY MODEL vs SIMPLE THRESHOLD")
    print("="*70)
    
    X = df[['health_factor']].copy()
    y = df['label'].values
    
    X['health_factor'] = X['health_factor'].replace([np.inf, -np.inf], np.nan)
    X['health_factor'] = X['health_factor'].fillna(X['health_factor'].median())
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # 1. XGBoost with only HF
    print("\n[1] XGBoost with ONLY health_factor:")
    print("-" * 70)
    
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=['health_factor'])
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=['health_factor'])
    
    model = xgb.train(
        {'objective': 'binary:logistic', 'device': 'cuda:1', 'tree_method': 'hist',
         'max_depth': 4, 'learning_rate': 0.1, 'seed': 42},
        dtrain, num_boost_round=100,
        evals=[(dtest, 'test')], verbose_eval=False
    )
    
    y_proba = model.predict(dtest)
    y_pred = (y_proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    
    print(f"  Precision: {precision_score(y_test, y_pred):.4f}")
    print(f"  Recall:    {recall_score(y_test, y_pred):.4f}")
    print(f"  F1:        {f1_score(y_test, y_pred):.4f}")
    print(f"  AUC:       {roc_auc_score(y_test, y_proba):.4f}")
    print(f"  Confusion: TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    
    # 2. Simple threshold rule (HF < 1.0)
    print("\n[2] Simple Rule: HF < 1.0 → liquidation")
    print("-" * 70)
    
    y_pred_rule = (X_test['health_factor'].values < 1.0).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_rule).ravel()
    
    print(f"  Precision: {precision_score(y_test, y_pred_rule):.4f}")
    print(f"  Recall:    {recall_score(y_test, y_pred_rule):.4f}")
    print(f"  F1:        {f1_score(y_test, y_pred_rule):.4f}")
    print(f"  Confusion: TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    
    # 3. Multiple thresholds
    print("\n[3] Threshold Analysis:")
    print("-" * 70)
    print(f"{'Threshold':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    
    for t in [0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50]:
        y_pred_t = (X_test['health_factor'].values < t).astype(int)
        if y_pred_t.sum() > 0:
            p = precision_score(y_test, y_pred_t)
            r = recall_score(y_test, y_pred_t)
            f = f1_score(y_test, y_pred_t)
            print(f"  HF < {t:.2f}  {p:>10.4f} {r:>10.4f} {f:>10.4f}")
    
    # 4. Critical zone analysis
    print("\n[4] Critical Zone (HF 1.0-1.5) - The Hard Cases:")
    print("-" * 70)
    
    test_df = X_test.copy()
    test_df['actual'] = y_test
    test_df['xgb_pred'] = y_pred
    
    cz = test_df[(test_df['health_factor'] >= 1.0) & (test_df['health_factor'] <= 1.5)]
    
    print(f"Total in critical zone: {len(cz):,}")
    print(f"  Class 1 (liquidated): {(cz['actual'] == 1).sum():,}")
    print(f"  Class 0 (active):     {(cz['actual'] == 0).sum():,}")
    
    if len(cz) > 0:
        # XGBoost accuracy in critical zone
        xgb_acc = (cz['actual'] == cz['xgb_pred']).mean()
        
        # Rule accuracy (HF < 1.0 in this zone is always 0 -> always predicts class 0)
        rule_acc = (cz['actual'] == 0).mean()  # Rule predicts 0 for all here
        
        print(f"\nIn critical zone:")
        print(f"  XGBoost accuracy: {xgb_acc:.2%}")
        print(f"  HF<1.0 rule accuracy: {rule_acc:.2%} (predicts safe for all)")
    
    # 5. Look at exact HF distribution
    print("\n[5] HF Distribution (Test Set):")
    print("-" * 70)
    
    for label in [0, 1]:
        subset = X_test[y_test == label]['health_factor']
        print(f"\nClass {label} ({(y_test == label).sum()} samples):")
        print(f"  Min:    {subset.min():.4f}")
        print(f"  25%:    {subset.quantile(0.25):.4f}")
        print(f"  Median: {subset.median():.4f}")
        print(f"  75%:    {subset.quantile(0.75):.4f}")
        print(f"  Max:    {subset.max():.4f}")
    
    # 6. Find overlap zone
    print("\n[6] OVERLAP DETECTION:")
    print("-" * 70)
    
    c0_max = X_test[y_test == 0]['health_factor'].quantile(0.05)  # 5th percentile of class 0
    c1_max = X_test[y_test == 1]['health_factor'].quantile(0.95)  # 95th percentile of class 1
    
    print(f"Class 0 5th percentile:  {c0_max:.4f}")
    print(f"Class 1 95th percentile: {c1_max:.4f}")
    
    if c0_max > c1_max:
        print(f"⚠️  NO OVERLAP - HF perfectly separates classes")
        print(f"   Gap: {c0_max - c1_max:.4f}")
    else:
        print(f"✅ Real overlap exists from HF {c0_max:.4f} to {c1_max:.4f}")


if __name__ == '__main__':
    main()
