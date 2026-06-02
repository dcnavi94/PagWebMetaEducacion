import glob
import os

files = glob.glob('public/*.html')
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Replace style and script
    content = content.replace('href="style.css"', 'href="style.min.css"')
    content = content.replace('src="script.js"', 'src="script.min.js"')
    
    # Add preload if not present
    preload_css = '<link rel="preload" href="style.min.css" as="style">\n    <link rel="preload" href="script.min.js" as="script">\n</head>'
    if 'rel="preload" href="style.min.css"' not in content:
        content = content.replace('</head>', preload_css)
        
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)

print("Files updated successfully")
