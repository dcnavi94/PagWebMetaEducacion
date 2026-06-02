import os
import glob

router_dir = "backend/app/routers"
router_files = glob.glob(os.path.join(router_dir, "*.py"))

for file in router_files:
    if os.path.basename(file) == "__init__.py":
        continue
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Revert syntax errors
    content = content.replace("def app.main._", "def _")
    content = content.replace("class app.main._", "class _")
    content = content.replace("async def app.main._", "async def _")
    
    with open(file, "w", encoding="utf-8") as f:
        f.write(content)

print("Fixed syntax errors.")
