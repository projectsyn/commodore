// main template for {{ cookiecutter.slug}}
local kap = import 'lib/kapitan.libjsonnet';
local kube = import 'lib/kube.libjsonnet';
local inv = kap.inventory();
// The hiera parameters for the component
local params = inv.parameters.{{ cookiecutter.parameter_key }};

// Define outputs below
{
}
