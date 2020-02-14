import configparser


def main():
    pipfile = configparser.ConfigParser()
    pipfile.read('Pipfile')
    for pkg in pipfile['packages']:
        version = pipfile['packages'][pkg].strip('"')
        if version == '*':
            print(pkg)
        else:
            print(f"{pkg}{version}")


if __name__ == "__main__":
    main()
