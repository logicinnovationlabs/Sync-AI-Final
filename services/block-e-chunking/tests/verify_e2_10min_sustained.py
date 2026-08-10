"""
E2 Verification: 10-minute sustained test with real rolling window calculation
Per Master Build Prompt v2.0 §8.4: E2 requires empirical rolling window from real data
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the real rolling window calculation script
from tests.calculate_real_rolling_window import calculate_real_rolling_window


async def verify_e2_sustained():
    """Run 10-minute sustained test with real rolling window calculation."""
    
    print("=" * 80)
    print("E2 VERIFICATION: 10-Minute Sustained Test with Real Rolling Window")
    print("=" * 80)
    
    # Run the real rolling window calculation which includes the 10-minute test
    success = await calculate_real_rolling_window()
    
    return success


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_e2_sustained())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
