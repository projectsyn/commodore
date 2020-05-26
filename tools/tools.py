from subprocess import call


def build_kapitan_helm_binding():
    call("./tools/build_kapitan_helm_binding.sh")


def autopep():
    call(['autopep8', '--in-place', '--aggressive', '--recursive', '--verbose', './'])


def local_reveal():
    call("./tools/reveal.sh")


def compile():
    call(['kapitan', 'compile', '-J', '.', 'dependencies/', '--refs-path', './catalog/refs'])
