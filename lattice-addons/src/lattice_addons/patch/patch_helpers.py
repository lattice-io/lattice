from wrapt import resolve_path, apply_patch
from wrapt import FunctionWrapper
from typing import Type, Set, Callable, Dict, Any


def _get_subclasses(cls: Type) -> Set[Type]:
    subclasses: Set[Type] = set()
    for sub_cls in cls.__subclasses__():
        subclasses.add(sub_cls)
        subclasses = subclasses.union(_get_subclasses(sub_cls))
    return subclasses


def get_subclasses(cls: Type) -> Set[Type]:
    return _get_subclasses(cls)


def get_type_object(module: str, cls: str) -> Type:
    # Resolve the path for a class method will make parent the class
    parent, _, _ = resolve_path(module, f'{cls}.__init__')
    return parent


def patch_methods(module: Any, cls: str, wrappers: Dict[str, Callable]) -> None:
    r""" Patch the instance methods of a target class using wrappers.

    :param module: The top-level module of the target class either as a module object or a string
    :param cls: The target class in the module as a string using relative import path. For example,
        for class ``mod.lib.A``, the `module` should be ``mod``, and the `class` should be ``lib.A``
    :param wrappers: A dictionary of wrappers for methods where keys are method names and values are the wrappers.
        The wrappers should have `"wrapt" style interfaces <https://github.com/GrahamDumpleton/wrapt/blob/develop/blog/11-safely-applying-monkey-patches-in-python.md#creating-a-decorator>`_
    """  # noqa: E501

    ty_obj = get_type_object(module, cls)

    for method, wrapper in wrappers.items():
        apply_patch(ty_obj, method, FunctionWrapper(getattr(ty_obj, method), wrapper))


def patch_methods_for_subclasses(module: Any, cls: str, wrappers: Dict[str, Callable]) -> None:
    r""" Patch the instance methods of the imported subclasses of a target class using wrappers.

    This functions depends ``__subclasses__`` to infer subclasses. If there new subclasses, consider to use
    :obj:`~.patch_methods_for_new_subclasses` instead.

    :param module: The top-level module of the target class either as a module object or a string
    :param cls: The target class in the module as a string using relative import path. For example,
        for class ``mod.lib.A``, the `module` should be ``mod``, and the `class` should be ``lib.A``
    :param wrappers: A dictionary of wrappers for methods where keys are method names and values are the wrappers.
        The wrappers should have `"wrapt" style interfaces <https://github.com/GrahamDumpleton/wrapt/blob/develop/blog/11-safely-applying-monkey-patches-in-python.md#creating-a-decorator>`_
    """  # noqa: E501

    ty_obj = get_type_object(module, cls)

    for sub_ty_obj in _get_subclasses(ty_obj):
        for method, wrapper in wrappers.items():
            apply_patch(sub_ty_obj, method, FunctionWrapper(getattr(sub_ty_obj, method), wrapper))


def patch_methods_for_new_subclasses(module: Any, cls: str, wrappers: Dict[str, Callable]) -> None:
    r""" Patch the instance methods of the newly created subclasses of a target class using wrappers.

    :param module: The top-level module of the target class either as a module object or a string
    :param cls: The target class in the module as a string using relative import path. For example,
        for class ``mod.lib.A``, the `module` should be ``mod``, and the `class` should be ``lib.A``
    :param wrappers: A dictionary of wrappers for methods where keys are method names and values are the wrappers.
        The wrappers should have `"wrapt" style interfaces <https://github.com/GrahamDumpleton/wrapt/blob/develop/blog/11-safely-applying-monkey-patches-in-python.md#creating-a-decorator>`_
    """  # noqa: E501

    ty_obj = get_type_object(module, cls)

    @classmethod  # type: ignore[misc]
    def init_subclass(c: Type) -> None:
        for method, wrapper in wrappers.items():
            setattr(c, method, FunctionWrapper(getattr(c, method), wrapper))

    apply_patch(ty_obj, '__init_subclass__', init_subclass)
