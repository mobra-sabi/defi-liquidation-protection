#!/usr/bin/env python3
"""
XGBoost Liquidation Prediction Model - GPU Training

Trains an XGBoost model to predict time until liquidation based on
position features. Uses GPU acceleration for fast training.

Target metrics:
- Precision: >72%
- False Positive Rate: <15%
- Median Lead Time: >10 minutes

Usage:
    python train_model.py --data-prefix ml_ready --gpu-id 1
"""

import os
import json
import logging
import argparse
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    precision_score, recall_score, f1_score, confusion_matrix
)
import matplotlib.pyplot as plt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
AI_ENGINE_DIR = Path(__file__).parent
DATA_DIR = AI_ENGINE_DIR.parent / 'data' / 'processed'
MODELS_DIR = AI_ENGINE_DIR / 'models'
MODELS_DIR.mkdir(exist_ok=True)


def load_data(data_prefix: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str], str]:
    """Load train/val/test datasets."""
    logger.info(f"Loading data with prefix '{data_prefix}'...")

    train_df = pd.read_parquet(DATA_DIR / f'{data_prefix}_train.parquet')
    val_df = pd.read_parquet(DATA_DIR / f'{data_prefix}_val.parquet')
    test_df = pd.read_parquet(DATA_DIR / f'{data_prefix}_test.parquet')

    # Load metadata
    with open(DATA_DIR / f'{data_prefix}_metadata.json', 'r') as f:
        metadata = json.load(f)

    features = metadata['feature_columns']
    target = metadata['target_column']

    logger.info(f"  ✓ Loaded {len(train_df)} train, {len(val_df)} val, {len(test_df)} test samples")
    logger.info(f"  ✓ {len(features)} features")

    return train_df, val_df, test_df, features, target


def convert_to_regression_target(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """
    Convert time_to_liquidation to binary classification target.
    We want to predict if liquidation will happen within certain time windows.
    """
    df = df.copy()

    # Create binary targets for different time horizons
    df['liquidation_15min'] = (df[target_col] <= 15).astype(int)
    df['liquidation_30min'] = (df[target_col] <= 30).astype(int)
    df['liquidation_60min'] = (df[target_col] <= 60).astype(int)

    return df


def train_xgboost_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    params: Dict,
    num_rounds: int = 500,
    early_stopping_rounds: int = 50
) -> xgb.Booster:
    """Train XGBoost model with GPU acceleration."""
    logger.info("Training XGBoost model...")
    logger.info(f"  GPU device: {params.get('device', 'cpu')}")
    logger.info(f"  Training samples: {len(X_train)}")
    logger.info(f"  Validation samples: {len(X_val)}")

    # Create DMatrix
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dval = xgb.DMatrix(X_val, label=y_val)

    # Training with early stopping
    start_time = time.time()

    evals = [(dtrain, 'train'), (dval, 'val')]
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=num_rounds,
        evals=evals,
        early_stopping_rounds=early_stopping_rounds,
        verbose_eval=50
    )

    training_time = time.time() - start_time
    logger.info(f"  ✓ Training completed in {training_time:.2f}s")
    logger.info(f"  ✓ Best iteration: {model.best_iteration}")
    logger.info(f"  ✓ Best score: {model.best_score:.4f}")

    return model


def evaluate_model(
    model: xgb.Booster,
    X_test: np.ndarray,
    y_test: np.ndarray,
    threshold: float = 0.5
) -> Dict:
    """Evaluate model performance."""
    logger.info("Evaluating model...")

    # Predictions
    dtest = xgb.DMatrix(X_test)
    y_pred_proba = model.predict(dtest)
    y_pred = (y_pred_proba >= threshold).astype(int)

    # Metrics
    metrics = {
        'precision': precision_score(y_test, y_pred),
        'recall': recall_score(y_test, y_pred),
        'f1': f1_score(y_test, y_pred),
        'mae': mean_absolute_error(y_test, y_pred_proba),
        'mse': mean_squared_error(y_test, y_pred_proba),
        'r2': r2_score(y_test, y_pred_proba),
    }

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()

    metrics['true_positives'] = int(tp)
    metrics['false_positives'] = int(fp)
    metrics['true_negatives'] = int(tn)
    metrics['false_negatives'] = int(fn)
    metrics['false_positive_rate'] = fp / (fp + tn) if (fp + tn) > 0 else 0
    metrics['true_positive_rate'] = tp / (tp + fn) if (tp + fn) > 0 else 0

    logger.info(f"  ✓ Precision: {metrics['precision']:.4f}")
    logger.info(f"  ✓ Recall: {metrics['recall']:.4f}")
    logger.info(f"  ✓ F1 Score: {metrics['f1']:.4f}")
    logger.info(f"  ✓ False Positive Rate: {metrics['false_positive_rate']:.4f}")
    logger.info(f"  ✓ True Positive Rate: {metrics['true_positive_rate']:.4f}")

    return metrics, y_pred_proba


def plot_feature_importance(model: xgb.Booster, feature_names: List[str], output_path: Path):
    """Plot and save feature importance."""
    importance = model.get_score(importance_type='gain')

    # Sort by importance
    importance_df = pd.DataFrame([
        {'feature': feature_names[int(k.replace('f', ''))], 'importance': v}
        for k, v in importance.items()
    ])
    importance_df = importance_df.sort_values('importance', ascending=False).head(20)

    # Plot
    plt.figure(figsize=(12, 8))
    plt.barh(importance_df['feature'], importance_df['importance'])
    plt.xlabel('Importance (Gain)')
    plt.title('Top 20 Feature Importances')
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    logger.info(f"  ✓ Feature importance plot saved to {output_path}")


def save_model(model: xgb.Booster, model_name: str, metadata: Dict):
    """Save model and metadata."""
    model_path = MODELS_DIR / f'{model_name}.json'
    model.save_model(str(model_path))

    metadata_path = MODELS_DIR / f'{model_name}_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"  ✓ Model saved to {model_path}")
    logger.info(f"  ✓ Metadata saved to {metadata_path}")


def main():
    parser = argparse.ArgumentParser(description='Train XGBoost Liquidation Model')
    parser.add_argument('--data-prefix', type=str, default='ml_ready',
                        help='Data file prefix')
    parser.add_argument('--gpu-id', type=int, default=1,
                        help='GPU device ID (default: 1 for RTX 3080)')
    parser.add_argument('--target-horizon', type=str, default='30min',
                        choices=['15min', '30min', '60min'],
                        help='Prediction time horizon')
    parser.add_argument('--threshold', type=float, default=0.5,
                        help='Classification threshold')

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("XGBOOST LIQUIDATION PREDICTION MODEL - GPU TRAINING")
    logger.info("=" * 70)
    logger.info(f"Configuration:")
    logger.info(f"  GPU ID: {args.gpu_id}")
    logger.info(f"  Target: liquidation within {args.target_horizon}")
    logger.info(f"  Threshold: {args.threshold}")
    logger.info("=" * 70)

    # Load data
    train_df, val_df, test_df, features, target_col = load_data(args.data_prefix)

    # Convert to classification target
    train_df = convert_to_regression_target(train_df, target_col)
    val_df = convert_to_regression_target(val_df, target_col)
    test_df = convert_to_regression_target(test_df, target_col)

    # Select target column
    target_map = {'15min': 'liquidation_15min', '30min': 'liquidation_30min', '60min': 'liquidation_60min'}
    target = target_map[args.target_horizon]

    X_train = train_df[features].values
    y_train = train_df[target].values
    X_val = val_df[features].values
    y_val = val_df[target].values
    X_test = test_df[features].values
    y_test = test_df[target].values

    logger.info(f"\nTarget distribution:")
    logger.info(f"  Train - Positive: {y_train.sum()}/{len(y_train)} ({100*y_train.mean():.1f}%)")
    logger.info(f"  Val - Positive: {y_val.sum()}/{len(y_val)} ({100*y_val.mean():.1f}%)")
    logger.info(f"  Test - Positive: {y_test.sum()}/{len(y_test)} ({100*y_test.mean():.1f}%)")

    # XGBoost parameters for GPU
    params = {
        'objective': 'binary:logistic',
        'eval_metric': ['auc', 'logloss'],
        'max_depth': 8,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 3,
        'gamma': 0.1,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'scale_pos_weight': len(y_train) / y_train.sum() - 1,  # Handle class imbalance
        'device': f'cuda:{args.gpu_id}',
        'tree_method': 'hist',
        'random_state': 42,
        'seed': 42
    }

    # Train model
    model = train_xgboost_model(
        X_train, y_train, X_val, y_val,
        params, num_rounds=1000, early_stopping_rounds=100
    )

    # Evaluate
    metrics, y_pred_proba = evaluate_model(model, X_test, y_test, args.threshold)

    # Plot feature importance
    plot_feature_importance(model, features, MODELS_DIR / f'xgb_{args.target_horizon}_importance.png')

    # Save model
    model_metadata = {
        'model_type': 'xgboost',
        'target': target,
        'target_horizon': args.target_horizon,
        'threshold': args.threshold,
        'gpu_id': args.gpu_id,
        'features': features,
        'n_features': len(features),
        'n_train_samples': len(X_train),
        'n_test_samples': len(X_test),
        'best_iteration': int(model.best_iteration),
        'best_score': float(model.best_score),
        'metrics': {k: float(v) for k, v in metrics.items()},
        'parameters': params
    }

    save_model(model, f'xgb_liquidation_predictor_{args.target_horizon}', model_metadata)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TRAINING COMPLETE")
    logger.info("=" * 70)
    logger.info(f"\nFinal Metrics:")
    logger.info(f"  Precision: {metrics['precision']:.2%}")
    logger.info(f"  Recall: {metrics['recall']:.2%}")
    logger.info(f"  F1 Score: {metrics['f1']:.4f}")
    logger.info(f"  False Positive Rate: {metrics['false_positive_rate']:.2%}")
    logger.info(f"  True Positive Rate: {metrics['true_positive_rate']:.2%}")

    # Check targets
    if metrics['precision'] >= 0.72 and metrics['false_positive_rate'] <= 0.15:
        logger.info("\n🎉 Model meets target criteria!")
    else:
        logger.info("\n⚠️  Model needs improvement:")
        if metrics['precision'] < 0.72:
            logger.info(f"    - Precision {metrics['precision']:.2%} < 72% target")
        if metrics['false_positive_rate'] > 0.15:
            logger.info(f"    - FPR {metrics['false_positive_rate']:.2%} > 15% target")

    logger.info(f"\nNext steps:")
    logger.info(f"  1. Deploy model to ai-engine/models/")
    logger.info(f"  2. Setup inference pipeline")
    logger.info(f"  3. Deploy smart contracts")


if __name__ == '__main__':
    main()
