import configparser


def main():
    pyproject = configparser.ConfigParser()
    pyproject.read('pyproject.toml')
    for pkg, version in pyproject['tool.poetry.dependencies'].items():
        if pkg == "python":
            continue
        version = version.strip('"')
        if version == '*':
            print(pkg)
        else:
            version = version.replace('^', '~=')
            print(f"{pkg}{version}")


if __name__ == "__main__":
    main()
