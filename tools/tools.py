from subprocess import call


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
