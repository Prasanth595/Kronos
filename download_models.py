"""
Kronos Model Download Script
Downloads tokenizer and Kronos-small model from HuggingFace Hub
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import Kronos, KronosTokenizer

def download_models():
    print("=" * 50)
    print("Kronos Model Downloader")
    print("=" * 50)
    
    print("\n[1/2] Downloading KronosTokenizer...")
    print("       Model: NeoQuasar/Kronos-Tokenizer-base")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    print("       [OK] Tokenizer downloaded successfully")
    
    print("\n[2/2] Downloading Kronos-small model...")
    print("       Model: NeoQuasar/Kronos-small")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    print("       [OK] Model downloaded successfully")
    
    print("\n" + "=" * 50)
    print("Download complete!")
    print(f"Model device: {next(model.parameters()).device}")
    print(f"Tokenizer device: {next(tokenizer.parameters()).device}")
    print("=" * 50)

if __name__ == "__main__":
    download_models()