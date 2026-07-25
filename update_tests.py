import os
import re

def update_test_file(filepath):
    if not os.path.exists(filepath):
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Import BoundValue
    if 'BoundValue' not in content:
        content = content.replace('from app.analysis.base import SetupSnapshot', 'from app.analysis.base import SetupSnapshot, BoundValue')
        content = content.replace('from app.analysis.base import AnalysisStrategy, SetupSnapshot, TuningRecommendationResult', 'from app.analysis.base import AnalysisStrategy, SetupSnapshot, TuningRecommendationResult, BoundValue')

    # Replace defaults in _default_setup and _dummy_setup
    def replacer(match):
        inner = match.group(1)
        # Find all param=value pairs and wrap in BoundValue if value is a float
        # This regex is a bit fragile, let's just do it manually for the known ones.
        return match.group(0)

    # Let's just modify the instantiation
    # Look for defaults = dict(...)
    def dict_repl(match):
        dict_body = match.group(1)
        new_body = re.sub(r'([a-zA-Z0-9_]+)=([0-9\.-]+)', r'\1=BoundValue(None, \2, None)', dict_body)
        return 'defaults = dict(' + new_body + ')'
    
    content = re.sub(r'defaults\s*=\s*dict\((.*?)\)', dict_repl, content, flags=re.DOTALL)
    
    # Also handle SetupSnapshot(tire_pressure_front=30.0, ...) in test_ollama_analyzer and test_gpu_queue
    def snap_repl(match):
        snap_body = match.group(1)
        new_body = re.sub(r'([a-zA-Z0-9_]+)=([0-9\.-]+)', r'\1=BoundValue(None, \2, None)', snap_body)
        return 'SetupSnapshot(' + new_body + ')'
        
    content = re.sub(r'SetupSnapshot\(\s*(tire_pressure_front=.*?)\)', snap_repl, content, flags=re.DOTALL)
    
    # Also handle overrides. Overrides might just be passed directly like _default_setup(camber_front=-3.0)
    # The overrides dictionary inside _default_setup is updated into defaults.
    # We should convert overrides to BoundValue inside _default_setup.
    def add_bound_conversion(match):
        return match.group(0) + '\n    overrides = {k: BoundValue(None, v, None) if isinstance(v, (int, float)) and k not in ["pi_rating", "hp", "weight_lbs"] else v for k, v in overrides.items()}'
    
    content = re.sub(r'defaults\.update\(overrides\)', add_bound_conversion, content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for filename in ['test_math_analyzer.py', 'test_tuning_goals.py', 'test_gpu_queue.py', 'test_ollama_analyzer.py']:
    update_test_file(os.path.join('tests', filename))
