'use client';

import { Canvas, useFrame } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

type Interaction = { x: number; y: number; dragX: number; dragY: number };

// Generate repeatable positions once, so rendering does not depend on random frames.
function makeGlobe() {
  const count = 340,
    radius = 2.15,
    goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const nodes: THREE.Vector3[] = [];
  const start: number[] = [];
  let seed = 14277;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let i = 0; i < count; i++) {
    const y = 1 - (2 * (i + 0.5)) / count;
    const ring = Math.sqrt(1 - y * y);
    const angle = i * goldenAngle;
    nodes.push(
      new THREE.Vector3(
        Math.cos(angle) * ring * radius,
        y * radius,
        Math.sin(angle) * ring * radius,
      ),
    );
    start.push(
      (random() - 0.5) * 8.2,
      (random() - 0.5) * 5.3,
      (random() - 0.5) * 2.6,
    );
  }
  const end = new Float32Array(
    nodes.flatMap((point) => [point.x, point.y, point.z]),
  );
  const edgeIndices: number[] = [];
  const seen = new Set<string>();
  nodes.forEach((point, index) => {
    const nearest = nodes
      .map((other, j) => ({ j, distance: point.distanceToSquared(other) }))
      .filter((candidate) => candidate.j !== index)
      .sort((a, b) => a.distance - b.distance)
      .slice(0, 4);
    for (const { j } of nearest) {
      const key = index < j ? `${index}:${j}` : `${j}:${index}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edgeIndices.push(index, j);
    }
  });
  // These stars never become graph nodes and remain scattered around the globe.
  const ambient: number[] = [];
  while (ambient.length < 220 * 3) {
    const x = (random() - 0.5) * 9.5,
      y = (random() - 0.5) * 6.1;
    if (Math.hypot(x, y) < 2.5) continue;
    ambient.push(x, y, (random() - 0.5) * 2);
  }
  return {
    start: new Float32Array(start),
    end,
    edgeIndices,
    ambient: new Float32Array(ambient),
  };
}

function Field({
  interaction,
  visible,
}: {
  interaction: React.RefObject<Interaction>;
  visible: React.RefObject<boolean>;
}) {
  const group = useRef<THREE.Group>(null);
  const pointsAttribute = useRef<THREE.BufferAttribute>(null);
  const linesAttribute = useRef<THREE.BufferAttribute>(null);
  const linesGeometry = useRef<THREE.BufferGeometry>(null);
  const spin = useRef(0),
    elapsed = useRef(0);
  const geometry = useMemo(makeGlobe, []);
  const positions = useMemo(() => geometry.start.slice(), [geometry]);
  const lines = useMemo(
    () => new Float32Array(geometry.edgeIndices.length * 3),
    [geometry],
  );
  useFrame((_, delta) => {
    if (!group.current || !visible.current || document.hidden) return;
    const step = Math.min(delta, 0.05);
    elapsed.current += step;
    spin.current += step * 0.055;
    const { x, y, dragX, dragY } = interaction.current;
    group.current.rotation.y = THREE.MathUtils.damp(
      group.current.rotation.y,
      spin.current + dragX + x * 0.3,
      4,
      step,
    );
    group.current.rotation.x = THREE.MathUtils.damp(
      group.current.rotation.x,
      dragY - y * 0.22,
      4,
      step,
    );
    if (
      pointsAttribute.current &&
      linesAttribute.current &&
      linesGeometry.current
    ) {
      for (let i = 0; i < positions.length / 3; i++) {
        const stagger = ((i % 23) / 23) * 1.5;
        const progress = THREE.MathUtils.clamp(
          (elapsed.current - 0.8 - stagger) / 5,
          0,
          1,
        );
        const eased = progress * progress * (3 - 2 * progress);
        for (let axis = 0; axis < 3; axis++) {
          const j = i * 3 + axis;
          positions[j] = THREE.MathUtils.lerp(
            geometry.start[j],
            geometry.end[j],
            eased,
          );
        }
      }
      for (let i = 0; i < geometry.edgeIndices.length; i++) {
        const source = geometry.edgeIndices[i] * 3;
        lines[i * 3] = positions[source];
        lines[i * 3 + 1] = positions[source + 1];
        lines[i * 3 + 2] = positions[source + 2];
      }
      pointsAttribute.current.needsUpdate = true;
      linesAttribute.current.needsUpdate = true;
      // Line segments appear in stages as the points settle into place.
      const edgeCount = geometry.edgeIndices.length / 2;
      const visibleEdges = Math.floor(
        edgeCount * THREE.MathUtils.clamp((elapsed.current - 2) / 6.5, 0, 1),
      );
      linesGeometry.current.setDrawRange(0, visibleEdges * 2);
    }
  });
  return (
    <>
      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[geometry.ambient, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          color="#c9d8c0"
          size={0.023}
          transparent
          opacity={0.55}
          sizeAttenuation
          depthWrite={false}
        />
      </points>
      <group ref={group}>
        <points>
          <bufferGeometry>
            <bufferAttribute
              ref={pointsAttribute}
              attach="attributes-position"
              args={[positions, 3]}
              usage={THREE.DynamicDrawUsage}
            />
          </bufferGeometry>
          <pointsMaterial
            color="#edf2e7"
            size={0.036}
            transparent
            opacity={0.9}
            sizeAttenuation
            depthWrite={false}
          />
        </points>
        <lineSegments>
          <bufferGeometry ref={linesGeometry}>
            <bufferAttribute
              ref={linesAttribute}
              attach="attributes-position"
              args={[lines, 3]}
              usage={THREE.DynamicDrawUsage}
            />
          </bufferGeometry>
          <lineBasicMaterial
            color="#a9c09d"
            transparent
            opacity={0.3}
            depthWrite={false}
          />
        </lineSegments>
      </group>
    </>
  );
}

export function ResearchField() {
  const interaction = useRef<Interaction>({ x: 0, y: 0, dragX: 0, dragY: 0 });
  const drag = useRef<{ id: number; x: number; y: number } | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const visible = useRef(false);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible.current = entry.isIntersecting;
      },
      { threshold: 0.15 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={container}
      className="research-field"
      aria-hidden="true"
      onPointerDown={(event) => {
        if (event.pointerType !== 'mouse' || event.button !== 0) return;
        drag.current = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        interaction.current.x =
          ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
        interaction.current.y =
          1 - ((event.clientY - bounds.top) / bounds.height) * 2;
        if (drag.current?.id === event.pointerId) {
          interaction.current.dragX += (event.clientX - drag.current.x) * 0.007;
          interaction.current.dragY = THREE.MathUtils.clamp(
            interaction.current.dragY +
              (event.clientY - drag.current.y) * 0.007,
            -1.2,
            1.2,
          );
          drag.current.x = event.clientX;
          drag.current.y = event.clientY;
        }
      }}
      onPointerUp={(event) => {
        if (drag.current?.id === event.pointerId) drag.current = null;
      }}
      onPointerCancel={() => {
        drag.current = null;
      }}
      onPointerLeave={() => {
        if (!drag.current) {
          interaction.current.x = 0;
          interaction.current.y = 0;
        }
      }}
    >
      <Canvas
        camera={{ position: [0, 0, 7.6], fov: 43 }}
        dpr={[1, 1.5]}
        frameloop="always"
      >
        <Field interaction={interaction} visible={visible} />
      </Canvas>
    </div>
  );
}
