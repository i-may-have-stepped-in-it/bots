#!/usr/bin/env python3
"""
Master script to apply all Phase 1 fixes.
Run this to apply critical fixes automatically.
"""

import sys
import subprocess
from pathlib import Path

# Add fixes directory to path
sys.path.insert(0, str(Path(__file__).parent))

from phase1.fix_voice_syntax import fix_voice_syntax
from phase1.fix_teamviewer import fix_teamviewer
from phase1.fix_token_bucket import fix_token_bucket
from phase1.fix_health_check import fix_health_check
from phase1.fix_ssl_config import fix_ssl_config


def main():
    """Apply all Phase 1 fixes."""
    print("=" * 60)
    print("Jennifer Bot - Phase 1 Critical Fixes")
    print("=" * 60)
    print()
    
    results = {}
    
    # Fix 1: Voice syntax
    print("\\n[1/4] Fixing voice_recv_class.py syntax errors...")
    print("-" * 40)
    results['voice'] = fix_voice_syntax()
    
    # Fix 2: Teamviewer
    print("\\n[2/4] Fixing teamviewer.py security issue...")
    print("-" * 40)
    results['teamviewer'] = fix_teamviewer()
    
    # Fix 3: Token bucket
    print("\\n[3/4] Fixing image_gen.py rate limiting...")
    print("-" * 40)
    results['token_bucket'] = fix_token_bucket()
    
    # Fix 4: Health check
    print("\\n[4/4] Adding health check file creation...")
    print("-" * 40)
    results['health_check'] = fix_health_check()
    
    # Fix 5: SSL Config
    print("\n[5/5] Creating smart SSL configuration...")
    print("-" * 40)
    results['ssl_config'] = fix_ssl_config()
    
    # Summary
    print("\\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {name:20} {status}")
    
    all_passed = all(results.values())
    
    print()
    if all_passed:
        print("🎉 All fixes applied successfully!")
        print()
        print("Next steps:")
        print("  1. Review the changes: git diff")
        print("  2. Update your .env file with new TeamViewer settings")
        print("  3. Update openclaw.py and image_gen.py to use SSLConfigManager")
        print("  4. Rebuild and restart: docker-compose up -d --build")
        return 0
    else:
        print("⚠️  Some fixes failed. Check the output above.")
        print()
        print("To rollback all changes:")
        print("  git checkout -- utils/voice_recv_class.py")
        print("  git checkout -- utils/teamviewer.py")
        print("  git checkout -- utils/image_gen.py")
        print("  git checkout -- bot/client.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
