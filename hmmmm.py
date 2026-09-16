from commands3 import Mechanism, Scheduler, requires_self, requiring


class MechanismOne(Mechanism):
    @requires_self()
    async def do_something(self):
        print("1: Doing something")


class MechanismTwo(Mechanism):
    @requires_self()
    async def do_something(self):
        print("2: Doing something")


mech1 = MechanismOne()
mech2 = MechanismTwo()


@requiring(mech1, mech2)
async def do_something():
    await mech1.do_something()
    print("Outer: Doing something")
    await mech2.do_something()


if __name__ == "__main__":
    Scheduler.get_default().schedule(do_something())
    Scheduler.get_default().run()
