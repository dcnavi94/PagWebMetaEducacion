import os
import glob
import re

router_dir = "backend/app/routers"
router_files = glob.glob(os.path.join(router_dir, "*.py"))

for file in router_files:
    if os.path.basename(file) == "__init__.py":
        continue
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Ensure app.main is imported
    if "import app.main" not in content:
        content = content.replace("from fastapi import APIRouter", "import app.main\nfrom fastapi import APIRouter")
        
    # Find all function calls that start with _ and don't have a dot before them
    # like _assign_curriculum_to_student(
    # Avoid replacing already prefixed ones like app.main._assign
    # Avoid replacing inner defs if any? There are no inner defs with _.
    def replacer(match):
        # The preceding character is group 1, the function name is group 2
        prefix = match.group(1)
        func_name = match.group(2)
        if prefix in ('.',): 
            return match.group(0) # Already has a dot, like app.main._foo
        if prefix in ('f', 's'): # def or class end char - simple check
            return match.group(0)
        return prefix + 'app.main._' + func_name + '('
        
    new_content = re.sub(r'([^\w\.]|^)_([a-zA-Z0-9_]+)\(', replacer, content)
    with open(file, "w", encoding="utf-8") as f:
        f.write(new_content)

print("Fixed helper function calls in routers.")
