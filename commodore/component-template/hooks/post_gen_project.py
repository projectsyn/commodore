import shutil

create_lib = "{{ cookiecutter.add_lib }}" == "y"

if not create_lib:
    shutil.rmtree("lib")
