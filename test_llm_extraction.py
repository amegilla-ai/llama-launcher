#!/usr/bin/env python3
"""
Test script for LLM parameter extraction.
Run this to test the new functionality before integrating into the main app.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.utils import save_param_references_llm, load_param_references
from shared.config import DEFAULT_LLM_ENDPOINT

def test_llm_extraction():
    """Test the LLM parameter extraction."""
    print("Testing LLM Parameter Extraction")
    print("=" * 40)
    
    # Test paths - update these for your system
    server_path = input("Enter path to llama-server binary: ").strip()
    cli_path = input("Enter path to llama-cli binary: ").strip()
    
    if not server_path or not cli_path:
        print("❌ Binary paths required")
        return
    
    # Test LLM endpoint
    llm_endpoint = input(f"LLM endpoint [{DEFAULT_LLM_ENDPOINT}]: ").strip()
    if not llm_endpoint:
        llm_endpoint = DEFAULT_LLM_ENDPOINT
    
    print(f"\nServer binary: {server_path}")
    print(f"CLI binary: {cli_path}")
    print(f"LLM endpoint: {llm_endpoint}")
    print("\nTesting extraction...")
    
    # Test extraction
    success, message = save_param_references_llm(server_path, cli_path, llm_endpoint)
    
    if success:
        print("✅ Success:", message)
        print("\nGenerated parameters:")
        params = load_param_references()
        for category, items in params.items():
            print(f"\n{category.upper()}:")
            for param, desc in items.items():
                print(f"  {param}: {desc}")
    else:
        print("❌ Error:", message)

if __name__ == "__main__":
    test_llm_extraction()
