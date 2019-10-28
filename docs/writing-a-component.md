# Writing a Commodore Component

Commodore components are bundles which contain templates and a component
class describing a component (e.g. a fully-configured Crossplane stack) for
consumption by Kapitan. Additionally a Commodore component can contain
postprocessing filters, which are arbitrary Jsonnet scripts that are executed
by Commodore after Kapitan has compiled the component.

## Quickstart

To kickstart developing a component, the following shell commands can be
executed to create a barebones, best-practice oriented directory layout. Make
sure you are in the directory in which you wish to develop your comopnent and
set the variable `COMPONENT` to the name of your component.

```shell
COMPONENT="<The Component Name>"
```

If the component name does not match the name of the Component's Git
repository, the variable `input_paths` in `kapitan.compile` must be adjusted
accordingly to use the Git repository name instead of the component name as
the first path component.

```shell
mkdir -p class component postprocess
cat <<EOF > README.md
# ${COMPONENT}

A commodore Component for ${COMPONENT}
EOF
cat <<EOF > class/${COMPONENT}.yml
parameters:
  kapitan:
    compile:
      - output_path: ${COMPONENT}
        input_type: jsonnet
        output_type: yaml
        input_paths:
          - ${COMPONENT}/component/main.jsonnet
EOF
cat <<EOF > component/main.jsonnet
local kap = import 'lib/kapitan.libjsonnet';
local kube = import 'lib/kube.libjsonnet';
local inv = kap.inventory();

// Define outputs below
{
}
EOF
cat <<EOF > postprocess/filters.yml
filters: []
EOF
```

After that, you can start developing your component by writing Jsonnet in
`component/main.jsonnet`.

If you do not require any postprocessing of the Kapitan output, you can delete
the whole `postprocess` folder in the component repository. Removing the
folder will make Commodore skip the postprocessing step for the component
completely.

## The component templates

The component templates can be any templating language that Kapitan can
handle. Currently Commodore supports Jsonnet, Jinja2, Kadet (alpha) and Helm
(alpha) as templating languages. This guide will use Jsonnet as the
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

Commodore ensures that Bitnami Labs's
[kube-libsonnet](https://github.com/bitnami-labs/kube-libsonnet)
is available as `lib/kube.libjsonnet`. This allows templates to reuse the
provided methods to abstract away a lot of the tedious bits of writing
Kubernetes objects.

As an illustration, below is an example `nginx` deployment which is written
using `kube-libsonnet`.

```jsonnet
local kube = import 'lib/kube.libjsonnet';

local deployment = kube.Deployment('test-nginx') {
  spec+: {
    template+: {
      spec+: {
        containers_+: {
          default: kube.Container('nginx') {
            image: 'nginx',
            ports_+: { http: { containerPort: 80 } }
          }
        }
      }
    }
  }
}
```


### Validating inventory schemas

Kapitan includes [JSON Schema](https://json-schema.org/), which can be used to
validate inventory section structures against schemas. To write schemas,
please refer to ["Understanding JSON Schema"](https://json-schema.org/understanding-json-schema/index.html).

Given the schema

```jsonnet
local section_schema = {
  type: "object",
  properties: {
    key1: { type: "string" },
    key2: { type: "int" },
    key3: { type: "string", pattern: "^prefix-[0-9]+$" }
  },
  required: [ 'key1', 'key2' ]
};
```

and the example inventory

```yaml
parameters:
  section_a:
    key1: test
    key2: 20
  section_b:
    key1: test
    key2: 20
    key3: prefix-0000
  section_c:
    key1: test
    key2: 50G
  section_d:
    key1: test
    key2: 20
    key3: other-2000
  section_e:
    key1: test
    key3: prefix-2000
```

we can validate the structure of each of `section_a`, `section_b` and
`section_c` using the `jsonschema()` function:

```jsonnet
local validation = kap.jsonschema(inv.parameters.section_X, section_schema);
assert validation.valid: validation.reason;
```

Validation of `section_a` and `section_b` succeeds and produces no output.

Validation of `section_c` fails with:

```
Jsonnet error: failed to compile schema_example.jsonnet:
 RUNTIME ERROR: '50G' is not of type 'integer'

Failed validating 'type' in schema['properties']['key2']:
    {'type': 'integer'}

On instance['key2']:
    '50G'
```

Validation of `section_d` fails with:

```
Jsonnet error: failed to compile schema_example.jsonnet:
 RUNTIME ERROR: 'other-2000' does not match '^prefix-[0-9]+$'

Failed validating 'pattern' in schema['properties']['key3']:
    {'pattern': '^prefix-[0-9]+$', 'type': 'string'}

On instance['key3']:
    'other-2000'
```

Validation of `section_e` fails with:

```
Jsonnet error: failed to compile schema_example.jsonnet:
 RUNTIME ERROR: 'key2' is a required property

Failed validating 'required' in schema:
    {'properties': {'key1': {'type': 'string'},
                    'key2': {'type': 'integer'},
                    'key3': {'pattern': '^prefix-[0-9]+$',
                             'type': 'string'}},
     'required': ['key1', 'key2'],
     'type': 'object'}

On instance:
    {'key1': 'test', 'key3': 'prefix-2000'}
```

If `validation.valid` is not true, the `assert` will fail, which aborts the
compilation, and the reason for the validation failure will be displayed.

## The component class

Commodore looks for the component class in `class/<component-name>.yml`. Since
Kapitan does only process files in the inventory which end with `.yml`, it's
important that the component class is named exactly as specified.

The component class provides Kapitan with the information that's necessary to
compile a component.

Commodore components will always be stored under
`dependencies/<component-name>` in Kapitan's working directory. Commodore
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
`compiled/target/<output_path>/<key>.yaml`. Filter authors can decide
themselves whether to write filters that overwrite their inputs, or not.
