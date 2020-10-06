import shutil

create_lib = "{{ cookiecutter.add_lib }}" == "y"
create_pp = "{{ cookiecutter.add_pp }}" == "y"

if not create_lib:
    shutil.rmtree("lib")
if not create_pp:
    shutil.rmtree("postprocess")
