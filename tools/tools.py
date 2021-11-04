from subprocess import call


def autopep():
    call(["autopep8", "--in-place", "--aggressive", "--recursive", "--verbose", "./"])


def local_reveal():
    call("./tools/reveal.sh")


def compile():
    call(
        [
            "kapitan",
            "compile",
            "-J",
            ".",
            "dependencies/",
            "--refs-path",
            "./catalog/refs",
        ]
    )
