from pythonforandroid.recipe import RustCompiledComponentsRecipe


class JiterRecipe(RustCompiledComponentsRecipe):
    version = "0.10.0"

    url = (
        "https://files.pythonhosted.org/packages/source/"
        "j/jiter/jiter-{version}.tar.gz"
    )

    site_packages_name = "jiter"


recipe = JiterRecipe()