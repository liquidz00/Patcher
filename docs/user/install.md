# Installation

Once prerequisites have been satisfied, Patcher can be installed via ``pip``:

```shell
$ python3 -m pip install --upgrade patcherctl
```

Optionally, beta releases of Patcher are released to [Test PyPI](https://test.pypi.org/project/patcherctl/) and can be installed via the following command:

```shell
$ python3 -m pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple patcherctl=={VERSION}
```

Where `{VERSION}` is the beta version you are looking to install, e.g. `1.3.4b2`.

```{note}
Installing beta versions of Patcher are meant only for testing features being developed and implemented. We encourage installing these versions for contribution purposes. For more information, visit the {ref}`contributing <contributing_index>` page.
```
