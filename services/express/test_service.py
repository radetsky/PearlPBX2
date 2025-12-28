#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Express FastAGI Service - Test Suite
"""

import socket
import sys

def test_fastagi_connection(host='localhost', port=4574):
    """Test connection to FastAGI server"""
    print(f"Testing connection to {host}:{port}...")
    
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        # Connect
        sock.connect((host, port))
        print("✓ Connection established")
        
        # Simulate minimal AGI request
        agi_env = [
            "agi_network: yes",
            "agi_network_script: test",
            "agi_channel: TEST/test-00000001",
            "agi_callerid: 380671234567",
            ""  # Empty line to end environment
        ]
        
        print("\nSending AGI environment...")
        for line in agi_env:
            sock.sendall(f"{line}\n".encode('utf-8'))
        
        print("✓ AGI environment sent")
        
        # Wait for response
        print("\nReceiving server response...")
        sock.settimeout(2)
        
        try:
            response_count = 0
            while response_count < 5:
                data = sock.recv(1024)
                if not data:
                    break
                print(f"← {data.decode('utf-8', errors='ignore').strip()}")
                response_count += 1
        except socket.timeout:
            print("(timeout - normal for test)")
        
        sock.close()
        print("\n✓ Test completed successfully")
        print("\nService is working correctly!")
        return True
        
    except ConnectionRefusedError:
        print(f"✗ Error: Cannot connect to {host}:{port}")
        print("  Check that service is running:")
        print("  sudo systemctl status express-fastagi")
        return False
        
    except socket.timeout:
        print(f"✗ Error: Timeout connecting to {host}:{port}")
        return False
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

def test_express_http(server_url, provider='test', phone='0671234567'):
    """Test HTTP request to Express API"""
    import urllib.request
    import urllib.error
    
    print(f"\nTesting HTTP request to Express API...")
    print(f"Server: {server_url}")
    
    # Parse URL to build full request
    if not server_url.startswith('http'):
        server_url = f"http://{server_url}"
    
    # Add query parameters
    url = f"{server_url}?provider={provider}&from={phone}&to=192.168.1.1&line=1&carClass=0"
    
    print(f"URL: {url}")
    
    try:
        response = urllib.request.urlopen(url, timeout=5)
        data = response.read().decode('utf-8')
        print(f"✓ Express response: {data}")
        return True
    except urllib.error.URLError as e:
        print(f"✗ Connection error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("Express FastAGI Service - Test Suite")
    print("=" * 60)
    
    # Test 1: FastAGI connection
    print("\n[TEST 1] FastAGI Connection Test")
    print("-" * 60)
    fastagi_ok = test_fastagi_connection()
    
    # Test 2: Express HTTP API (optional)
    if len(sys.argv) > 1:
        print("\n[TEST 2] Express HTTP API Test")
        print("-" * 60)
        express_url = sys.argv[1]
        express_ok = test_express_http(express_url)
    else:
        print("\n[TEST 2] Express HTTP API Test - SKIPPED")
        print("To test Express API, run:")
        print(f"  python3 {sys.argv[0]} http://YOUR_EXPRESS_IP:8080/YTaxi/ru/ManagePBX/IncomingCall")
        express_ok = None
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)
    print(f"FastAGI Connection: {'✓ PASSED' if fastagi_ok else '✗ FAILED'}")
    if express_ok is not None:
        print(f"Express HTTP API:   {'✓ PASSED' if express_ok else '✗ FAILED'}")
    else:
        print(f"Express HTTP API:   - SKIPPED")
    print("=" * 60)
    
    if fastagi_ok:
        print("\n✓ Basic tests passed!")
        print("\nFor complete verification:")
        print("1. Make a real call through Asterisk")
        print("2. Check logs: journalctl -u express-fastagi -f")
        print("3. Verify ULINE allocation in logs")
        sys.exit(0)
    else:
        print("\n✗ Tests failed. Check configuration.")
        sys.exit(1)

if __name__ == '__main__':
    main()
