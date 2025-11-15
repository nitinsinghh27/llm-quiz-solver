#!/usr/bin/env python3
"""
Test script for the quiz endpoint
"""
import requests
import json
from config import Config

def test_health():
    """Test the health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get('http://localhost:5001/health')
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        print("✓ Health check passed\n")
        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}\n")
        return False

def test_quiz_endpoint():
    """Test the quiz endpoint with demo URL"""
    print("Testing quiz endpoint with demo URL...")

    payload = {
        "email": Config.EMAIL,
        "secret": Config.SECRET,
        "url": "https://tds-llm-analysis.s-anand.net/demo"
    }

    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(
            'http://localhost:5001/quiz',
            json=payload,
            timeout=180  # 3 minutes timeout
        )

        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        if response.status_code == 200:
            print("✓ Quiz endpoint test passed\n")
            return True
        else:
            print("✗ Quiz endpoint test failed\n")
            return False

    except Exception as e:
        print(f"✗ Quiz endpoint test failed: {e}\n")
        return False

def test_invalid_secret():
    """Test with invalid secret (should return 403)"""
    print("Testing with invalid secret...")

    payload = {
        "email": Config.EMAIL,
        "secret": "wrong_secret",
        "url": "https://tds-llm-analysis.s-anand.net/demo"
    }

    try:
        response = requests.post('http://localhost:5001/quiz', json=payload)

        if response.status_code == 403:
            print(f"✓ Correctly rejected invalid secret (403)\n")
            return True
        else:
            print(f"✗ Expected 403, got {response.status_code}\n")
            return False

    except Exception as e:
        print(f"✗ Test failed: {e}\n")
        return False

def test_invalid_json():
    """Test with invalid JSON (should return 400)"""
    print("Testing with invalid JSON...")

    try:
        response = requests.post(
            'http://localhost:5001/quiz',
            data="not json",
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 400:
            print(f"✓ Correctly rejected invalid JSON (400)\n")
            return True
        else:
            print(f"✗ Expected 400, got {response.status_code}\n")
            return False

    except Exception as e:
        print(f"✗ Test failed: {e}\n")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Quiz Endpoint Test Suite")
    print("=" * 60)
    print()

    results = []

    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Invalid JSON", test_invalid_json()))
    results.append(("Invalid Secret", test_invalid_secret()))
    results.append(("Valid Quiz Request", test_quiz_endpoint()))

    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")

    print()
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)
