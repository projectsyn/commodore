# Writing a Commodore Component

Commodore components are bundles which contain templates and a component
class describing a component (e.g. a fully-configured Crossplane stack) for
consumption by Kapitan.  Additionally a Commodore component can contain
postprocessing filters, which are arbitrary Jsonnet scripts that are executed
by Commodore after Kapitan has compiled the component.

## Quickstart

TODO: quickstart guide

## The component templates

The component templates can be any templating language that Kapitan can
handle. Currently Kadet supports Jsonnet, Jinja2, Kadet (alpha) and Helm
(alpha) as templating languages.  This guide will use Jsonnet as the
templating language for any examples.

Component templates can be stored anywhere in the Commodore component
repository, as long as they're correctly referenced by the component class.

From a template, the [Kapitan Inventory](https://kapitan.dev/inventory/) --
which is managed by Commodore -- can be accessed with

```jsonnet
local kap = import "lib/kapitan.libjsonnet";
local inv = kap.inventory();
```

Any variables which are configured in any class in the inventory under
`parameters` can then be retrieved via

```jsonnet
inv.parameters.section.subsection.value
```

## The component class

Commodore looks for the component class in `class/<component-name>.yml`. Since
Kapitan does only process files in the inventory which end with `.yml`, it's
important that the component class is named exactly as specified.

The component class provides Kapitan with the information that's necessary to
compile a component.

Commodore components will always be stored under
`dependencies/<component-name>` in Kapitan's working directory.  Commodore
configures Kapitan to look for inputs in the working directory and in
`dependencies`. To ensure that template file names cannot cause conflicts
between different components, the component class will always have to specify
inputs in the form `<component-name>/path/to/the/input.jsonnet`, the component
class will always have to specify inputs in the form
`<component-name>/path/to/the/input.jsonnet`. For example:

```yaml
parameters:
  kapitan:
    compile:
      - output_path: crossplane
        input_type: jsonnet
        output_type: yaml
        input_paths:
          - crossplane/component/main.jsonnet
```

To avoid name collisions in the output, each component should specify the
output path as the component's name for all compile instructions.

### Rendering Helm charts with Kapitan

See [Kapitan's documentation](https://kapitan.dev/compile/#helm).

It is strongly suggested that each component downloads helm charts into
`dependencies/<component-name>` to avoid weird interactions if multiple
components build upon the same helm chart.

## Postprocessing filters

Postprocessing filters can be arbitrary Jsonnet. Other templating languages
are not supported at the moment. The format of the Jsonnet is inspired by
Kapitan and the postprocessor expects that each filter outputs a JSON object
where the keys are used as the name of the resulting output files. For each
file, the value of the object's key is rendered as YAML in that file.

Postprocessing filters are defined in `postprocess/filters.yml`, which is
inspired by the Kapitan compile instructions, but simplified as currently only
one input and output type are supported.

A sample `postprocess/filters.yml` might look like

```yaml
filters:
  - output_path: crossplane/01_helmchart/crossplane
    filter: add_namespace_to_helm_output.jsonnet
```

Commodore provides a `commodore.libjsonnet` Jsonnet library which can be used
by Jsonnet filters to access the Kapitan inventory and to load YAML files:

```jsonnet
local commodore = import 'lib/commodore.libjsonnet';
local inv = commodore.inventory();
```

The `inventory` function returns an object that behaves identically to the
object returned from `kapitan.libjsonnet`'s `inventory` function.

Additionally, each Jsonnet filter is executed with external variables
`component` and `target` set to the name of the component to which the filter
belongs and the name of the Kapitan compilation target respectively.

Commodore also provides `yaml_load` as a native callback to Jsonnet. This
allows filters to read in YAML files:

```jsonnet
local object = commodore.yaml_load('/path/to/input.yaml');
```

The value of each key of the Jsonnet output object is dumped as YAML to
`compiled/target/<output_path>/<key>.yaml`.  Filter authors can decide
themselves whether to write filters that overwrite their inputs, or not.
