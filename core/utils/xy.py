
class XY:
    """A class to represent 2-tuple value"""
    __slots__ = ('__data',)

    def __init__(self,
                 x: int | float,
                 y: int | float,
                 z: int | float | None=None):

        if not self.__validate(x, y, z or 0):
            raise TypeError("Arguments must be 'float' or 'int' type")

        self.__data: list[int | float] = [x, y, z]

    def __validate(self, *args):
        return all(isinstance(a, (int, float)) for a in list(args))

    def __str__(self):
        if self.z is not None:
            return f"({self.x}, {self.y}, {self.z})"
        return f"({self.x}, {self.y})"

    def __repr__(self):
        return self.__str__()

    def __getitem__(self, item: int) -> int | float:
        return self.__data[item]

    def __setitem__(self, idx: int, value: int | float):
        if not isinstance(idx, int):
            raise TypeError("Index must be 'int' type")
        if not self.__validate(value):
            raise TypeError("Value must be 'float' or 'int' type")
        if not 0 <= idx <= 2:
            raise IndexError("Index must be 0, 1 or 2")
        self.__data[idx] = value

    def max(self) -> int | float:
        return max(n for n in self.__data if n is not None)

    def min(self) -> int | float:
        return min(n for n in self.__data if n is not None)

    @property
    def x(self) -> int | float:
        return self.__data[0]

    @property
    def y(self) -> int | float:
        return self.__data[1]

    @property
    def z(self) -> int | float:
        return self.__data[2]

    @property
    def xy(self) -> list[int | float]:
        return self.__data[:2]

    @property
    def xyz(self) -> list[int | float]:
        return self.__data.copy()


if __name__ == '__main__':
    xy = XY(0, 1)
    try:
        assert xy.x == 0, 'fail 0.0'
        assert xy.y == 1, 'fail 0.1'
        assert xy.z is None, 'fail 0.2'
        assert xy.xy == [0, 1], 'fail 0.3'
        assert xy.xyz == [0, 1, None], 'fail 0.4'
    except AssertionError as e:
        print('failed 0')
        print(e)
    else:
        print('success 0')

    xy = XY(0, 1, 2)
    try:
        xy[0] = -0.124129047102120947
        xy[1] = 1234129047102120947
        xy[2] = -3456789047102120947
    except IndexError as e:
        print('failed 1')
        print(e)
    else:
        print('success 1')

    try:
        xy[0] = '1.107029'
    except TypeError as e:
        print('success 2')
    else:
        print('failed 2')

    try:
        xy['1'] = 5
    except TypeError as e:
        print('success 3')
    else:
        print('failed 3')

    try:
        xy[10000] = 5
    except IndexError as e:
        print('success 4')
    else:
        print('failed 4')

    try:
        xy = XY('1', 0x1)
    except TypeError:
        print('success 5')
    else:
        print('failed 5')

    print(xy)
