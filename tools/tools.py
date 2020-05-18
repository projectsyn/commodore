from subprocess import call, run


def build_kapitan_helm_binding():
    call("./tools/build_kapitan_helm_binding.sh")


def autopep():
    call(['autopep8', '--in-place', '--aggressive', '--recursive', '--verbose', './'])


def local_reveal():
    call("./tools/reveal.sh")


def compile():
    call(['kapitan', 'compile', '-J', '.', 'dependencies/', '--refs-path', './catalog/refs'])


def test():
    arguments = input("Enter tox arguments:")
    run('docker run -it --rm -v $PWD:/src:ro -v $PWD/.dtox:/app/.tox docker.io/painless/tox {}'.format(arguments), shell=True)


def update_requirements():
    call(['tox', '-e', 'requirements'])
