import shutil

create_lib = "{{ cookiecutter.add_lib }}" == "y"
add_golden = "{{ cookiecutter.add_golden }}" == "y"

if not create_lib:
    shutil.rmtree("lib")

if not add_golden:
    shutil.rmtree("tests/golden")
