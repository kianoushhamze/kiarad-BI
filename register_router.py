with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

if "proformas_router" not in text:
    lines = text.splitlines(keepends=True)
    new_lines = ["from proformas import router as proformas_router\n"]
    for line in lines:
        new_lines.append(line)
        if "app = FastAPI" in line:
            new_lines.append("app.include_router(proformas_router)\n")
    with open("api.py", "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print("✓ proformas_router registered in api.py")
else:
    print("✓ proformas_router is already registered.")
