import test from "node:test";
import assert from "node:assert/strict";

import {
  chooseBuddyIdleAnimationAction,
  isBuddyRoamTargetReached,
  resolveBuddyRoamFacing,
  resolveBuddyRoamStepPosition,
  resolveBuddyVirtualCursorFollowTargetPosition,
  resolveMascotMoveDurationMs,
  resolveVirtualCursorOrbitAngle,
  resolveVirtualCursorOrbitPosition,
} from "./buddyMascotMotionModel.ts";

test("mascot motion model keeps move durations deterministic when random is supplied", () => {
  assert.equal(resolveMascotMoveDurationMs(360, "fixed"), 360);
  assert.equal(resolveMascotMoveDurationMs(360, "random", () => 0.5), 540);
  assert.equal(chooseBuddyIdleAnimationAction(() => 0), "tail-switch");
  assert.equal(chooseBuddyIdleAnimationAction(() => 0.99), "virtual-cursor-chase");
});

test("mascot motion model resolves roam steps and facing without spin states", () => {
  const current = { x: 100, y: 100 };
  const target = { x: 300, y: 100 };
  const next = resolveBuddyRoamStepPosition(current, target, { width: 500, height: 400 });

  assert.deepEqual(next, { x: 196, y: 100 });
  assert.equal(isBuddyRoamTargetReached(next, target), false);
  assert.equal(resolveBuddyRoamFacing(next.x - current.x), "right");
  assert.equal(resolveBuddyRoamFacing(-20), "left");
  assert.equal(resolveBuddyRoamFacing(1), "front");
});

test("mascot motion model keeps virtual cursor orbit and follow targets bounded", () => {
  const viewport = { width: 500, height: 400 };
  const buddyPosition = { x: 300, y: 220 };
  const orbitPosition = resolveVirtualCursorOrbitPosition(0, buddyPosition, viewport);
  const orbitAngle = resolveVirtualCursorOrbitAngle(orbitPosition, buddyPosition);
  const followTarget = resolveBuddyVirtualCursorFollowTargetPosition(
    buddyPosition,
    { x: 20, y: 20 },
    viewport,
    90,
  );

  assert.ok(Math.abs(orbitAngle) < 0.05);
  assert.ok(orbitPosition.x >= 16 && orbitPosition.x <= viewport.width - 42 - 16);
  assert.ok(orbitPosition.y >= 16 && orbitPosition.y <= viewport.height - 42 - 16);
  assert.ok(followTarget.x >= 16 && followTarget.x <= viewport.width - 96 - 16);
  assert.ok(followTarget.y >= 16 && followTarget.y <= viewport.height - 96 - 16);
});
