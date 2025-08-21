"""
設置專案目錄結構
"""
import os

directories = [
    'data',
    'data/configs',
    'data/schedules',
    'data/training_data',
    'data/exports',
    'tests',
    'tests/unit',
    'tests/integration',
    'tests/fixtures'
]

for directory in directories:
    os.makedirs(directory, exist_ok=True)
    print(f"Created directory: {directory}")

print("Directory structure setup complete!")