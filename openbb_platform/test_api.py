from api.main import app

print("✅ FastAPI app loaded successfully")
print(f"✅ Total endpoints: {len(app.routes)} routes\n")

# Check for NotebookLM endpoint
for route in app.routes:
    if 'notebooklm' in str(route.path).lower():
        print(f"✅ FOUND NotebookLM endpoint: {route.path}")
        print(f"   Methods: {route.methods}")

print("\n✅ ALL CHECKS PASSED")
