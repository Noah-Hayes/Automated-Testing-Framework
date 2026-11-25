from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Callable


# 1. Sample Application Under Test (Headless Galasteroids Logic)

SW, SH = 1920, 1080
GALAGA_THRESHOLD = 5000


@dataclass
class Player:
    x: float = SW / 2
    y: float = SH / 2
    angle: float = 0.0
    w: int = 75
    h: int = 75

    def turnLeft(self) -> None:
        self.angle += 2.5

    def turnRight(self) -> None:
        self.angle -= 2.5

    def moveForward(self) -> None:
        rad = math.radians(self.angle + 90)
        self.x += math.cos(rad) * 3
        self.y -= math.sin(rad) * 3
        self.updateLocation()

    def updateLocation(self) -> None:
        if self.x > SW + 50:
            self.x = 0
        elif self.x < -self.w:
            self.x = SW
        if self.y < -50:
            self.y = SH
        elif self.y > SH + 50:
            self.y = 0


@dataclass
class Asteroid:
    rank: int  # 1, 2, or 3
    x: float
    y: float


class GameSession:
    """Testable application core extracted from game loop rules"""

    def __init__(self) -> None:
        self.player = Player()
        self.lives = 3
        self.score = 0
        self.galagaMode = False
        self.gameover = False
        self.asteroids: list[Asteroid] = []

    def shootAsteroid(self, asteroid: Asteroid) -> list[Asteroid]:
        if asteroid not in self.asteroids:
            raise ValueError("Asteroid not present in active session.")

        self.asteroids.remove(asteroid)
        spawned: list[Asteroid] = []

        if asteroid.rank == 3:
            self.score += 10
            spawned = [
                Asteroid(rank=2, x=asteroid.x, y=asteroid.y),
                Asteroid(rank=2, x=asteroid.x, y=asteroid.y),
            ]
        elif asteroid.rank == 2:
            self.score += 20
            spawned = [
                Asteroid(rank=1, x=asteroid.x, y=asteroid.y),
                Asteroid(rank=1, x=asteroid.x, y=asteroid.y),
            ]
        elif asteroid.rank == 1:
            self.score += 30
        else:
            raise ValueError(f"Invalid asteroid rank: {asteroid.rank}")

        self.asteroids.extend(spawned)
        self.checkPhaseTransition()
        return spawned

    def hitAlien(self) -> None:
        if not self.galagaMode:
            raise RuntimeError("Alien hits are only valid during Galaga mode.")
        self.score += 100

    def takeDamage(self) -> None:
        if self.gameover:
            return
        self.lives -= 1
        if self.lives <= 0:
            self.lives = 0
            self.gameover = True

    def checkPhaseTransition(self) -> None:
        if self.score >= GALAGA_THRESHOLD and not self.galagaMode and not self.gameover:
            self.galagaMode = True
            self.asteroids.clear()
            self.player.x = SW / 2
            self.player.y = SH - 100
            self.player.angle = 0.0


# 2. Reusable Testing Framework Components

class TestAssertionError(AssertionError):
    """Raised when a framework assertion fails"""


class Assert:
    """Reusable assertion helpers with clear diagnostic messages"""

    @staticmethod
    def equal(actual: Any, expected: Any, message: str = "") -> None:
        if actual != expected:
            detail = f"{message} | " if message else ""
            raise TestAssertionError(f"{detail}Expected {expected!r}, got {actual!r}")

    @staticmethod
    def true(condition: bool, message: str = "Condition was False") -> None:
        if not condition:
            raise TestAssertionError(message)

    @staticmethod
    def false(condition: bool, message: str = "Condition was True") -> None:
        if condition:
            raise TestAssertionError(message)

    @staticmethod
    def inRange(value: float, low: float, high: float, message: str = "") -> None:
        if not (low <= value <= high):
            detail = f"{message} | " if message else ""
            raise TestAssertionError(f"{detail}Value {value} not in [{low}, {high}]")

    @staticmethod
    def raises(exc_type: type[BaseException], fn: Callable[..., Any], *args: Any) -> None:
        try:
            fn(*args)
        except exc_type:
            return
        except Exception as other:
            raise TestAssertionError(
                f"Expected {exc_type.__name__}, but raised {type(other).__name__}: {other}"
            )
        raise TestAssertionError(
            f"Expected {exc_type.__name__} to be raised, but nothing was raised"
        )


@dataclass
class TestResult:
    suite: str
    name: str
    status: str          # "PASS" | "FAIL" | "ERROR"
    duration_ms: float
    message: str = ""


class TestSuite:
    """Base class for grouping reusable automated test cases"""

    name: str = "BaseSuite"

    def setup(self) -> None:
        """Override to initialize fresh state before each test"""

    def teardown(self) -> None:
        """Override to clean up after each test"""

    def discoverTests(self) -> list[str]:
        return sorted(
            attr for attr in dir(self)
            if attr.startswith("test_") and callable(getattr(self, attr))
        )


class TestRunner:
    """Executes test suites and generates structured pass/fail reports"""

    def __init__(self) -> None:
        self.suites: list[TestSuite] = []
        self.results: list[TestResult] = []

    def register(self, suite: TestSuite) -> None:
        self.suites.append(suite)

    def runAll(self) -> list[TestResult]:
        self.results.clear()
        for suite in self.suites:
            for test_name in suite.discoverTests():
                test_fn = getattr(suite, test_name)
                start = time.perf_counter()
                status = "PASS"
                message = ""

                try:
                    suite.setup()
                    test_fn()
                except TestAssertionError as exc:
                    status = "FAIL"
                    message = str(exc)
                except Exception as exc:
                    status = "ERROR"
                    message = f"{type(exc).__name__}: {exc}"
                finally:
                    try:
                        suite.teardown()
                    except Exception as cleanup_exc:
                        status = "ERROR"
                        message = f"Teardown failed: {cleanup_exc}"

                elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
                self.results.append(
                    TestResult(
                        suite=suite.name,
                        name=test_name,
                        status=status,
                        duration_ms=elapsed_ms,
                        message=message,
                    )
                )
        return self.results

    def buildSummary(self) -> dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        errors = sum(1 for r in self.results if r.status == "ERROR")
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate_pct": round((passed / total) * 100, 1) if total else 0.0,
            "overall_status": "PASS" if (failed == 0 and errors == 0 and total > 0) else "FAIL",
            "results": [asdict(r) for r in self.results],
        }

    def printReport(self) -> None:
        summary = self.buildSummary()
        print("=" * 68)
        print("AUTOMATED TEST EXECUTION REPORT")
        print("=" * 68)
        for r in self.results:
            print(f"[{r.status:<5}] {r.suite}.{r.name} ({r.duration_ms:.2f} ms)")
            if r.message:
                print(f"        -> {r.message}")
        print("-" * 68)
        print(
            f"Total: {summary['total']} | Passed: {summary['passed']} | "
            f"Failed: {summary['failed']} | Errors: {summary['errors']} | "
            f"Pass Rate: {summary['pass_rate_pct']}% | Overall: {summary['overall_status']}"
        )
        print("=" * 68)

    def saveJsonReport(self, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.write_text(json.dumps(self.buildSummary(), indent=2), encoding="utf-8")
        return path


# 3. Reusable Domain Test Suites (Validating Sample App & Valid Inputs)

class MovementTestSuite(TestSuite):
    name = "MovementTests"

    def setup(self) -> None:
        self.session = GameSession()

    def test_valid_rotation_angles(self) -> None:
        self.session.player.turnLeft()
        Assert.equal(self.session.player.angle, 2.5, "turnLeft increments angle")
        self.session.player.turnRight()
        Assert.equal(self.session.player.angle, 0.0, "turnRight decrements angle")

    def test_forward_movement_moves_upward_at_zero_angle(self) -> None:
        start_y = self.session.player.y
        self.session.player.moveForward()
        Assert.equal(self.session.player.x, SW / 2, "X stays centered at angle 0")
        Assert.equal(self.session.player.y, start_y - 3, "Y decreases by 3 px")

    def test_screen_wrap_right_edge(self) -> None:
        self.session.player.x = SW + 51
        self.session.player.updateLocation()
        Assert.equal(self.session.player.x, 0, "Wraps from right edge to x=0")


class CombatAndScoringTestSuite(TestSuite):
    name = "CombatAndScoringTests"

    def setup(self) -> None:
        self.session = GameSession()

    def test_valid_asteroid_ranks_scoring_and_splitting(self) -> None:
        cases = [
            (3, 10, 2, 2),  # rank 3 -> +10 pts, spawns 2 rank-2 asteroids
            (2, 20, 2, 1),  # rank 2 -> +20 pts, spawns 2 rank-1 asteroids
            (1, 30, 0, 0),  # rank 1 -> +30 pts, spawns 0 asteroids
        ]
        for rank, expected_pts, expected_children, child_rank in cases:
            self.session = GameSession()
            target = Asteroid(rank=rank, x=400, y=300)
            self.session.asteroids.append(target)

            children = self.session.shootAsteroid(target)
            Assert.equal(self.session.score, expected_pts, f"Rank {rank} score")
            Assert.equal(len(children), expected_children, f"Rank {rank} split count")
            for child in children:
                Assert.equal(child.rank, child_rank, "Child rank matches")

    def test_invalid_asteroid_rank_raises_value_error(self) -> None:
        bad = Asteroid(rank=99, x=100, y=100)
        self.session.asteroids.append(bad)
        Assert.raises(ValueError, self.session.shootAsteroid, bad)


class PhaseAndLifecycleTestSuite(TestSuite):
    name = "PhaseAndLifecycleTests"

    def setup(self) -> None:
        self.session = GameSession()

    def testGalagaPhaseTriggersAt5000Points(self) -> None:
        self.session.score = 4970
        small = Asteroid(rank=1, x=200, y=200)
        extra = Asteroid(rank=2, x=500, y=500)
        self.session.asteroids.extend([small, extra])

        self.session.shootAsteroid(small)
        Assert.equal(self.session.score, 5000)
        Assert.true(self.session.galagaMode, "Galaga mode activates at 5000 points")
        Assert.equal(len(self.session.asteroids), 0, "Asteroids cleared on transition")
        Assert.equal(self.session.player.y, SH - 100, "Player locked near bottom")

    def testGalagaAlienHitAwards100Points(self) -> None:
        self.session.score = 5000
        self.session.checkPhaseTransition()
        self.session.hitAlien()
        Assert.equal(self.session.score, 5100)

    def testThreeHitsTriggerGameOver(self) -> None:
        for _ in range(3):
            self.session.takeDamage()
        Assert.equal(self.session.lives, 0)
        Assert.true(self.session.gameover, "Game over when lives reach 0")


# 4. Entry Point

def main() -> int:
    runner = TestRunner()
    runner.register(MovementTestSuite())
    runner.register(CombatAndScoringTestSuite())
    runner.register(PhaseAndLifecycleTestSuite())

    runner.runAll()
    runner.printReport()
    report_file = runner.saveJsonReport("test_report.json")
    print(f"JSON report written to: {report_file.resolve()}")

    summary = runner.buildSummary()
    return 0 if summary["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())