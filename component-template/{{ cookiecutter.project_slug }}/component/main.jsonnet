// main template for {{ cookiecutter.component }}
local kap = import 'lib/kapitan.libjsonnet';
local kube = import 'lib/kube.libjsonnet';
local inv = kap.inventory();
// The hiera parameters for the component
local params = inv.parameters.{{ cookiecutter.component }};

// Define outputs below
{
}
