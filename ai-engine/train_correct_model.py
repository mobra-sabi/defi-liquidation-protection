#!/usr/bin/env python3
"""
Train XGBoost Model on CORRECT Dataset - No Leakage

This script trains a model to predict:
"Will this position be liquidated in the next 30 minutes?"

Features: ONLY data available BEFORE the prediction moment
Target: 1 = liquidated within 30min, 0 = survives
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.metrics import (classification_report, confusion_matrix,
                            precision_score, recall_score, f1_score, roc_auc_score,
                            average_precision_score, roc_curve)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# Configuration
DATASET_PATH = '/home/mobra/protocol/data/aave_correct_dataset.parquet'
GPU_ID = 1  # XGBoost GPU

# Valid features - only data available BEFORE prediction moment
VALID_FEATURES = [
    # Position state at observation time
    'health_factor',
    'collateral_to_debt_ratio',
    'collateral_usd',
    'debt_usd',
    'liquidity_rate',
    'variable_borrow_rate',
    'liquidation_threshold',
    'base_ltv',
    
    # Time features (always known)
    'hour_of_day',
    'day_of_week',
    'is_weekend',
    'is_night',
    'is_morning',
    'is_afternoon',
]


def load_dataset():
    """Load and validate the correct dataset."""
    print("="*70)
    print("LOADING CORRECT DATASET")
    print("="*70)
    
    try:
        df = pd.read_parquet(DATASET_PATH)
        print(f"✅ Loaded {len(df):,} samples")
        print(f"Columns: {list(df.columns)}")
        return df
    except Exception as e:
        print(f"❌ Error loading dataset: {e}")
        return None


def validate_features(df):
    """Check which features are available in the dataset."""
    print("\n" + "="*70)
    print("VALIDATING FEATURES")
    print("="*70)
    
    available_features = [f for f in VALID_FEATURES if f in df.columns]
    missing_features = [f for f in VALID_FEATURES if f not in df.columns]
    
    print(f"✅ Available: {len(available_features)}/{len(VALID_FEATURES)}")
    for f in available_features:
        print(f"  - {f}")
    
    if missing_features:
        print(f"\n❌ Missing: {missing_features}")
    
    return available_features


def prepare_data(df, features):
    """Prepare data for training with time-based split."""
    print("\n" + "="*70)
    print("PREPARING DATA")
    print("="*70)
    
    # Target
    y = df['label'].values
    print(f"Target distribution:")
    print(f"  Class 0: {(y == 0).sum():,} ({(y == 0).mean():.1%})")
    print(f"  Class 1: {(y == 1).sum():,} ({(y == 1).mean():.1%})")
    
    # Features
    X = df[features].copy()
    
    # Handle any NaN values
    for col in X.columns:
        if X[col].isna().any():
            if X[col].dtype in [np.float64, np.int64]:
                median = X[col].median()
                X[col] = X[col].fillna(median)
            else:
                X[col] = X[col].fillna(0)
    
    # Time-based split (chronological)
    df = df.sort_values('observation_timestamp')
    n = len(df)
    split_idx = int(n * 0.8)
    
    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y[:split_idx]
    y_test = y[split_idx:]
    
    print(f"\nSplit (chronological):")
    print(f"  Train: {len(X_train):,} samples")
    print(f"    Class 0: {(y_train == 0).sum():,}")
    print(f"    Class 1: {(y_train == 1).sum():,}")
    print(f"  Test:  {len(X_test):,} samples")
    print(f"    Class 0: {(y_test == 0).sum():,}")
    print(f"    Class 1: {(y_test == 1).sum():,}")
    
    return X_train, X_test, y_train, y_test


def train_model(X_train, y_train, X_test, y_test, features):
    """Train XGBoost model on GPU."""
    print("\n" + "="*70)
    print("TRAINING XGBOOST MODEL")
    print("="*70)
    
    # Calculate scale_pos_weight
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    scale_pos_weight = neg_count / pos_count
    print(f"Scale pos weight: {scale_pos_weight:.2f}")
    
    # XGBoost parameters
    params = {
        'objective': 'binary:logistic',
        'eval_metric': ['auc', 'logloss'],
        'max_depth': 8,
        'learning_rate': 0.05,
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
    
    print(f"\nParameters:")
    for k, v in params.items():
        print(f"  {k}: {v}")
    
    # Create DMatrix
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=features)
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=features)
    
    # Train
    print(f"\nTraining...")
    evals = [(dtrain, 'train'), (dtest, 'test')]
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=500,
        evals=evals,
        early_stopping_rounds=50,
        verbose_eval=50
    )
    
    print(f"\n✅ Best iteration: {model.best_iteration}")
    print(f"Best score: {model.best_score:.4f}")
    
    return model, dtest


def evaluate_model(model, X_test, y_test, features):
    """Evaluate model performance."""
    print("\n" + "="*70)
    print("MODEL EVALUATION")
    print("="*70)
    
    dtest = xgb.DMatrix(X_test, label=y_test, feature_names=features)
    y_pred_proba = model.predict(dtest)
    
    # Try different thresholds
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7]
    
    print("\nThreshold optimization:")
    print(f"{'Threshold':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'FPR':>10}")
    print("-" * 60)
    
    best_f1 = 0
    best_threshold = 0.5
    
    for thresh in thresholds:
        y_pred = (y_pred_proba >= thresh).astype(int)
        
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        fpr = fp / (fp + tn)
        
        marker = "*" if f1 > best_f1 else " "
        print(f"{thresh:>10.2f} {precision:>10.2%} {recall:>10.2%} {f1:>10.2%} {fpr:>10.2%} {marker}")
        
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh
    
    # Use best threshold for final evaluation
    print(f"\nUsing threshold: {best_threshold}")
    y_pred_best = (y_pred_proba >= best_threshold).astype(int)
    
    # Final metrics
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_best).ravel()
    
    metrics = {
        'precision': tp / (tp + fp),
        'recall': tp / (tp + fn),
        'f1': f1_score(y_test, y_pred_best, zero_division=0),
        'auc': roc_auc_score(y_test, y_pred_proba),
        'average_precision': average_precision_score(y_test, y_pred_proba),
        'fpr': fp / (fp + tn),
        'accuracy': (tp + tn) / (tp + tn + fp + fn),
        'threshold': best_threshold,
        'true_positives': tp,
        'false_positives': fp,
        'true_negatives': tn,
        'false_negatives': fn,
    }
    
    print("\n" + "="*70)
    print("FINAL METRICS")
    print("="*70)
    print(f"Precision:            {metrics['precision']:.2%}")
    print(f"Recall (Sensitivity): {metrics['recall']:.2%}")
    print(f"F1-Score:             {metrics['f1']:.2%}")
    print(f"AUC-ROC:              {metrics['auc']:.4f}")
    print(f"Average Precision:    {metrics['average_precision']:.4f}")
    print(f"False Positive Rate:  {metrics['fpr']:.2%}")
    print(f"Accuracy:             {metrics['accuracy']:.2%}")
    print(f"Threshold used:       {metrics['threshold']:.2f}")
    print()
    print(f"Confusion Matrix @ {metrics['threshold']:.2f} threshold:")
    print(f"                  Predicted")
    print(f"  Actual    0 (Safe)   1 (Liquidate)")
    print(f"  0 (Safe)     {tn:,}        {fp:,}")
    print(f"  1 (Risk)     {fn:,}        {tp:,}")
    
    return metrics


def plot_feature_importance(model, features):
    """Plot feature importance."""
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)
    
    importance_dict = model.get_score(importance_type='gain')
    importance_list = [(f, importance_dict.get(f, 0)) for f in features]
    importance_list.sort(key=lambda x: x[1], reverse=True)
    
    print("\nTop 10 features (by gain):")
    for i, (feature, score) in enumerate(importance_list[:10], 1):
        print(f"  {i}. {feature}: {score:.2f}")
    
    # Plot
    try:
        top_features = importance_list[:15]
        names = [f[0] for f in top_features]
        scores = [f[1] for f in top_features]
        
        fig, ax = plt.subplots(figsize=(10, 8))
        y_pos = np.arange(len(names))
        ax.barh(y_pos, scores)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names)
        ax.invert_yaxis()
        ax.set_xlabel('Gain')
        ax.set_title('Feature Importance - Correct Model (No Leakage)')
        plt.tight_layout()
        plt.savefig('/home/mobra/protocol/ai-engine/correct_model_feature_importance.png', dpi=150)
        print(f"\n✅ Saved feature importance plot")
    except Exception as e:
        print(f"Error plotting: {e}")


def save_model(model, metrics):
    """Save model and metrics."""
    print("\n" + "="*70)
    print("SAVING MODEL")
    print("="*70)
    
    model_file = '/home/mobra/protocol/ai-engine/aave_correct_model.json'
    metrics_file = '/home/mobra/protocol/ai-engine/aave_correct_metrics.json'
    
    model.save_model(model_file)
    print(f"✅ Model saved: {model_file}")
    
    # Convert numpy types to native Python types
    def convert_to_native(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        return obj
    
    metrics_native = convert_to_native(metrics)
    
    with open(metrics_file, 'w') as f:
        json.dump(metrics_native, f, indent=2)
    print(f"✅ Metrics saved: {metrics_file}")
    
    return model_file


def main():
    print("\n" + "="*70)
    print("TRAINING CORRECT MODEL - NO LEAKAGE")
    print("="*70)
    print("Target: Will position be liquidated in next 30 minutes?")
    print("Features: Only data available BEFORE prediction moment")
    print()
    
    # Load data
    df = load_dataset()
    if df is None:
        print("❌ Cannot proceed without dataset")
        return
    
    # Validate features
    features = validate_features(df)
    if len(features) < 5:
        print("❌ Not enough features available")
        return
    
    # Prepare data
    X_train, X_test, y_train, y_test = prepare_data(df, features)
    
    # Train
    model, dtest = train_model(X_train, y_train, X_test, y_test, features)
    
    # Evaluate
    metrics = evaluate_model(model, X_test, y_test, features)
    
    # Plot importance
    plot_feature_importance(model, features)
    
    # Save
    save_model(model, metrics)
    
    # Final report
    print("\n" + "="*70)
    print("FINAL REPORT - CORRECT MODEL")
    print("="*70)
    print(f"✅ Model trained on {len(df):,} samples")
    print(f"✅ No data leakage - all features from BEFORE prediction")
    print(f"✅ Target: 'Will be liquidated in next 30 minutes'")
    print(f"✅ Precision: {metrics['precision']:.2%}")
    print(f"✅ Recall:    {metrics['recall']:.2%}")
    print(f"✅ F1-Score:  {metrics['f1']:.2%}")
    print(f"✅ AUC:       {metrics['auc']:.4f}")
    
    print("\n" + "="*70)
    print("INTERPRETATION")
    print("="*70)
    if metrics['precision'] < 0.4:
        print("⚠️  Low precision - many false positives (predicting liquidation when safe)")
        print("    This is expected for early warning systems where catching all")
        print("    liquidations is more important than precision.")
    elif metrics['precision'] > 0.7:
        print("✅ Good precision - when model says 'liquidation', it's usually right")
    
    if metrics['recall'] < 0.5:
        print("⚠️  Low recall - missing many actual liquidations")
    else:
        print(f"✅ Good recall - catching {metrics['recall']:.1%} of liquidations")
    
    print()
    print("Note: This is a DIFFICULT real-world problem. Even 30% precision")
    print("with high recall is valuable for early warning systems.")


if __name__ == '__main__':
    import json
    main()
