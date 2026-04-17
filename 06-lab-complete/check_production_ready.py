import os
import sys


def check(name: str, passed: bool, detail: str = "") -> dict:
    icon = "[OK]" if passed else "[X]"
    print(f"  {icon} {name}" + (f" - {detail}" if detail else ""))
    return {"name": name, "passed": passed}


def run_checks() -> bool:
    results = []
    base = os.path.dirname(__file__)

    print("\n" + "=" * 55)
    print("  Production Readiness Check - Day 12 Lab")
    print("=" * 55)

    print("\nRequired Files")
    results.append(check("Dockerfile exists", os.path.exists(os.path.join(base, "Dockerfile"))))
    results.append(check("docker-compose.yml exists", os.path.exists(os.path.join(base, "docker-compose.yml"))))
    results.append(check(".dockerignore exists", os.path.exists(os.path.join(base, ".dockerignore"))))
    results.append(check(".env.example exists", os.path.exists(os.path.join(base, ".env.example"))))
    results.append(check("requirements.txt exists", os.path.exists(os.path.join(base, "requirements.txt"))))
    results.append(
        check(
            "railway.toml or render.yaml exists",
            os.path.exists(os.path.join(base, "railway.toml")) or os.path.exists(os.path.join(base, "render.yaml")),
        )
    )

    print("\nSecurity")
    env_file = os.path.join(base, ".env")
    gitignore = os.path.join(base, ".gitignore")
    root_gitignore = os.path.join(base, "..", ".gitignore")

    env_ignored = False
    for path in [gitignore, root_gitignore]:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                if ".env" in handle.read():
                    env_ignored = True
                    break

    results.append(
        check(
            ".env in .gitignore",
            env_ignored,
            "Add .env to .gitignore." if not env_ignored else "",
        )
    )

    secrets_found = []
    for rel_path in ["app/main.py", "app/config.py", "app/llm.py"]:
        path = os.path.join(base, rel_path)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            for bad in ["sk-", "password123", "hardcoded"]:
                if bad in content:
                    secrets_found.append(f"{rel_path}:{bad}")

    results.append(
        check(
            "No hardcoded secrets in code",
            len(secrets_found) == 0,
            ", ".join(secrets_found) if secrets_found else "",
        )
    )

    print("\nAPI Endpoints")
    main_py = os.path.join(base, "app", "main.py")
    if os.path.exists(main_py):
        with open(main_py, encoding="utf-8") as handle:
            content = handle.read()
        results.append(check("/health endpoint defined", '"/health"' in content or "'/health'" in content))
        results.append(check("/ready endpoint defined", '"/ready"' in content or "'/ready'" in content))
        results.append(check("Authentication implemented", "api_key" in content.lower() or "verify_token" in content))
        results.append(check("Rate limiting implemented", "rate_limit" in content.lower() or "429" in content))
        results.append(check("Graceful shutdown (SIGTERM)", "SIGTERM" in content))
        results.append(check("Structured logging (JSON)", "json.dumps" in content or '"event"' in content))
    else:
        results.append(check("app/main.py exists", False, "Create app/main.py."))

    print("\nDocker")
    dockerfile = os.path.join(base, "Dockerfile")
    if os.path.exists(dockerfile):
        with open(dockerfile, encoding="utf-8") as handle:
            content = handle.read()
        results.append(check("Multi-stage build", "AS builder" in content or "AS runtime" in content))
        results.append(check("Non-root user", "useradd" in content or "USER " in content))
        results.append(check("HEALTHCHECK instruction", "HEALTHCHECK" in content))
        results.append(check("Slim base image", "slim" in content or "alpine" in content))

    dockerignore = os.path.join(base, ".dockerignore")
    if os.path.exists(dockerignore):
        with open(dockerignore, encoding="utf-8") as handle:
            content = handle.read()
        results.append(check(".dockerignore covers .env", ".env" in content))
        results.append(check(".dockerignore covers __pycache__", "__pycache__" in content))

    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    pct = round(passed / total * 100)

    print("\n" + "=" * 55)
    print(f"  Result: {passed}/{total} checks passed ({pct}%)")
    if pct == 100:
        print("  PRODUCTION READY")
    elif pct >= 80:
        print("  Almost there. Fix the failed items above.")
    elif pct >= 60:
        print("  Good progress. Several items still need attention.")
    else:
        print("  Not ready yet. Review the checklist carefully.")
    print("=" * 55 + "\n")
    return pct == 100


if __name__ == "__main__":
    sys.exit(0 if run_checks() else 1)
