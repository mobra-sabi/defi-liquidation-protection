#!/usr/bin/env python3
"""
System Check Script for DeFi AI Liquidation Protection Protocol

Verifies:
1. GPU availability and CUDA support
2. PyTorch GPU functionality
3. XGBoost GPU functionality
4. Required Python packages
5. Data collection capability
6. Network connectivity to TheGraph

Usage:
    python scripts/system_check.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Add protocol root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_success(text: str):
    """Print success message."""
    print(f"  ✓ {text}")

def print_error(text: str):
    """Print error message."""
    print(f"  ✗ {text}")

def print_warning(text: str):
    """Print warning message."""
    print(f"  ⚠ {text}")

def check_gpus():
    """Check GPU availability via nvidia-smi."""
    print_header("GPU HARDWARE CHECK")

    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,memory.total,temperature.gpu,utilization.gpu',
             '--format=csv,noheader'],
            capture_output=True,
            text=True,
            check=True
        )

        gpus = result.stdout.strip().split('\n')
        total_vram = 0

        print(f"\n  Found {len(gpus)} GPU(s):")
        print("  " + "-" * 66)

        for gpu_line in gpus:
            parts = gpu_line.split(', ')
            idx, name, memory, temp, util = parts
            vram_gb = int(memory.replace(' MiB', '')) / 1024
            total_vram += vram_gb
            print(f"  GPU {idx}: {name}")
            print(f"    Memory: {vram_gb:.2f} GB | Temp: {temp} | Utilization: {util}")

        print("  " + "-" * 66)
        print(f"  Total VRAM: {total_vram:.2f} GB")
        print_success(f"All {len(gpus)} GPUs accessible")

        return True, len(gpus), total_vram

    except FileNotFoundError:
        print_error("nvidia-smi not found. NVIDIA drivers not installed?")
        return False, 0, 0
    except subprocess.CalledProcessError as e:
        print_error(f"nvidia-smi failed: {e}")
        return False, 0, 0

def check_pytorch():
    """Check PyTorch installation and GPU support."""
    print_header("PYTORCH GPU CHECK")

    try:
        import torch

        print(f"\n  PyTorch version: {torch.__version__}")
        print(f"  CUDA available: {torch.cuda.is_available()}")

        if torch.cuda.is_available():
            print(f"  CUDA version: {torch.version.cuda}")
            print(f"  Number of GPUs: {torch.cuda.device_count()}")

            # Test each GPU
            print("\n  Testing GPU access:")
            for i in range(torch.cuda.device_count()):
                try:
                    # Allocate small tensor on each GPU
                    tensor = torch.randn(100, 100, device=f'cuda:{i}')
                    _ = tensor.sum().item()
                    props = torch.cuda.get_device_properties(i)
                    print_success(f"GPU {i}: {torch.cuda.get_device_name(i)} - OK")
                    print(f"    Memory: {props.total_memory / 1024**3:.2f} GB")
                    print(f"    Compute capability: {props.major}.{props.minor}")
                except Exception as e:
                    print_error(f"GPU {i}: Failed - {e}")

            # Test GPU computation
            print("\n  Testing GPU computation:")
            for i in range(torch.cuda.device_count()):
                try:
                    a = torch.randn(1000, 1000, device=f'cuda:{i}')
                    b = torch.randn(1000, 1000, device=f'cuda:{i}')
                    c = torch.matmul(a, b)
                    print_success(f"GPU {i}: Matrix multiplication - OK")
                except Exception as e:
                    print_error(f"GPU {i}: Computation failed - {e}")

            return True
        else:
            print_error("CUDA not available. PyTorch using CPU only.")
            return False

    except ImportError:
        print_error("PyTorch not installed. Run: pip install torch")
        return False

def check_xgboost():
    """Check XGBoost installation and GPU support."""
    print_header("XGBOOST GPU CHECK")

    try:
        import xgboost as xgb
        import numpy as np

        print(f"\n  XGBoost version: {xgb.__version__}")

        # Check GPU build
        build_info = xgb.build_info()
        has_cuda = build_info.get('USE_CUDA', False)
        print(f"  Built with CUDA: {has_cuda}")

        if not has_cuda:
            print_warning("XGBoost not compiled with GPU support")

        # Test GPU training
        print("\n  Testing XGBoost GPU training:")

        # Create sample data
        X = np.random.randn(10000, 50).astype(np.float32)
        y = np.random.randint(0, 2, 10000)
        dtrain = xgb.DMatrix(X, label=y)

        # Test on each GPU
        for gpu_id in range(min(3, 5)):  # Test up to 3 GPUs
            try:
                params = {
                    'device': f'cuda:{gpu_id}',
                    'max_depth': 6,
                    'eta': 0.1,
                    'objective': 'binary:logistic',
                    'eval_metric': 'logloss'
                }
                model = xgb.train(params, dtrain, num_boost_round=10)
                print_success(f"GPU {gpu_id}: Training - OK")
            except Exception as e:
                if gpu_id == 0:
                    print_error(f"GPU {gpu_id}: Training failed - {e}")
                # Stop testing if first GPU fails
                break

        return True

    except ImportError:
        print_error("XGBoost not installed. Run: pip install xgboost")
        return False

def check_packages():
    """Check required Python packages."""
    print_header("PYTHON PACKAGES CHECK")

    required_packages = [
        ('torch', 'PyTorch'),
        ('xgboost', 'XGBoost'),
        ('transformers', 'Hugging Face Transformers'),
        ('datasets', 'Hugging Face Datasets'),
        ('pandas', 'Pandas'),
        ('pyarrow', 'PyArrow'),
        ('numpy', 'NumPy'),
        ('requests', 'Requests'),
        ('web3', 'Web3.py'),
        ('scikit-learn', 'Scikit-learn'),
        ('python-dotenv', 'python-dotenv'),
    ]

    all_ok = True
    print()

    for package, name in required_packages:
        try:
            __import__(package)
            print_success(f"{name} ({package})")
        except ImportError:
            print_error(f"{name} ({package}) - NOT INSTALLED")
            all_ok = False

    return all_ok

def check_network():
    """Check network connectivity to TheGraph."""
    print_header("NETWORK CONNECTIVITY CHECK")

    import requests
    from dotenv import load_dotenv

    load_dotenv()

    subgraph_url = os.getenv('AAVE_V3_SUBGRAPH_URL',
                             'https://api.thegraph.com/subgraphs/name/aave/protocol-v3')

    print(f"\n  Testing connection to: {subgraph_url}")

    try:
        # Simple GraphQL introspection query
        query = {"query": "{ __typename }"}
        response = requests.post(
            subgraph_url,
            json=query,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            print_success("Connection successful")
            print(f"  Response time: {response.elapsed.total_seconds():.2f}s")
            return True
        else:
            print_error(f"Connection failed: HTTP {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        print_error("Connection timeout")
        return False
    except requests.exceptions.ConnectionError:
        print_error("Connection error - check network/internet")
        return False
    except Exception as e:
        print_error(f"Connection error: {e}")
        return False

def check_disk_space():
    """Check available disk space."""
    print_header("DISK SPACE CHECK")

    import shutil

    data_dir = Path(__file__).parent.parent / 'data'
    data_dir.mkdir(exist_ok=True)

    stat = shutil.disk_usage(data_dir)

    free_gb = stat.free / (1024**3)
    total_gb = stat.total / (1024**3)

    print(f"\n  Data directory: {data_dir}")
    print(f"  Free space: {free_gb:.2f} GB / {total_gb:.2f} GB")

    if free_gb < 10:
        print_warning("Low disk space! Need at least 10 GB for data collection.")
        return False
    else:
        print_success(f"Sufficient disk space ({free_gb:.2f} GB)")
        return True

def main():
    """Run all system checks."""
    print("\n" + "=" * 70)
    print("  DEFI AI LIQUIDATION PROTECTION PROTOCOL - SYSTEM CHECK")
    print("=" * 70)
    print("\n  Checking system readiness for protocol deployment...")

    results = {}

    # Run all checks
    results['gpus'] = check_gpus()
    results['pytorch'] = check_pytorch()
    results['xgboost'] = check_xgboost()
    results['packages'] = check_packages()
    results['network'] = check_network()
    results['disk'] = check_disk_space()

    # Summary
    print_header("SYSTEM CHECK SUMMARY")

    checks = [
        ('GPU Hardware', results['gpus'][0] if isinstance(results['gpus'], tuple) else results['gpus']),
        ('PyTorch GPU', results['pytorch']),
        ('XGBoost GPU', results['xgboost']),
        ('Python Packages', results['packages']),
        ('Network Connectivity', results['network']),
        ('Disk Space', results['disk']),
    ]

    passed = sum(1 for _, result in checks if result)
    total = len(checks)

    print()
    for name, result in checks:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status:8} - {name}")

    print("\n" + "=" * 70)
    print(f"  RESULT: {passed}/{total} checks passed")
    print("=" * 70)

    if passed == total:
        print("\n  🎉 All systems ready! You can now start data collection.")
        print("\n  Next steps:")
        print("    1. cd protocol/data")
        print("    2. python fetch_liquidations.py")
        return 0
    else:
        print("\n  ⚠️  Some checks failed. Please fix the issues above before proceeding.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
