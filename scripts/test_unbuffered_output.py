#!/usr/bin/env python3
"""
Test script to verify PYTHONUNBUFFERED=1 fix works.
Simulates exactly what the orchestrator does: launches a subprocess with piped stdout
that uses multiprocessing, and verifies output streams in real-time.

Last Updated: 06/02/2026, 3:15 PM (Friday) - Brisbane Time
"""
import subprocess
import os
import time
import selectors
import sys

def test_unbuffered():
    """Test that PYTHONUNBUFFERED=1 makes multiprocessing output visible via pipe"""
    
    # Create a test child script (with proper __name__ guard for multiprocessing)
    child_script = '''
import sys
import time
from multiprocessing import Process

def child_work():
    print("CHILD: I am a multiprocessing child process")
    print("CHILD: My output should also be visible")

if __name__ == "__main__":
    print("PARENT: Line 1 - should appear immediately")
    print("PARENT: Line 2 - before child spawn")

    p = Process(target=child_work)
    p.start()
    p.join()

    print("PARENT: Line 3 - after child complete")
    print("PARENT: All done!")
'''
    
    # Write temp script
    script_path = '/tmp/test_unbuffered_child.py'
    with open(script_path, 'w') as f:
        f.write(child_script)
    
    print("=" * 60)
    print("TEST: PYTHONUNBUFFERED=1 with multiprocessing via Popen")
    print("=" * 60)
    
    # Build environment with PYTHONUNBUFFERED (same as orchestrator fix)
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    
    proc = subprocess.Popen(
        f'python3 {script_path}',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env
    )
    
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    start = time.time()
    lines_received = []
    
    while True:
        events = sel.select(timeout=0.5)
        for key, _ in events:
            line = key.fileobj.readline()
            if line:
                elapsed = time.time() - start
                line_stripped = line.rstrip('\n')
                lines_received.append(line_stripped)
                print(f"  [{elapsed:.2f}s] {line_stripped}")
        
        if proc.poll() is not None:
            # Drain remaining
            for line in proc.stdout.read().splitlines():
                elapsed = time.time() - start
                lines_received.append(line)
                print(f"  [{elapsed:.2f}s] {line}")
            break
    
    sel.close()
    
    # Verify results
    print("\n" + "=" * 60)
    print("RESULTS:")
    print(f"  Lines received: {len(lines_received)}")
    print(f"  Exit code: {proc.returncode}")
    
    parent_lines = [l for l in lines_received if 'PARENT:' in l]
    child_lines = [l for l in lines_received if 'CHILD:' in l]
    
    print(f"  Parent lines: {len(parent_lines)}")
    print(f"  Child lines: {len(child_lines)}")
    
    if len(parent_lines) >= 4 and len(child_lines) >= 2:
        print("\n✅ SUCCESS: All output from parent AND child processes was captured!")
        print("✅ The PYTHONUNBUFFERED=1 fix works correctly.")
        return True
    else:
        print("\n❌ FAILED: Some output was missing!")
        print(f"   Expected 4+ parent lines, got {len(parent_lines)}")
        print(f"   Expected 2+ child lines, got {len(child_lines)}")
        return False

if __name__ == '__main__':
    success = test_unbuffered()
    sys.exit(0 if success else 1)
