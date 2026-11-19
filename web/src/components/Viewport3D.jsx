import React, { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, Lightformer, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

const stlLoader = new STLLoader();

function decodeStlB64(b64) {
  if (!b64) return null;
  const bin = atob(b64);
  const len = bin.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = bin.charCodeAt(i);
  }
  const geom = stlLoader.parse(bytes.buffer);
  geom.computeVertexNormals();
  return geom;
}

function PartMesh({ part, viewMode, explode, color, visible }) {
  const meshRef = useRef();
  const b64 = viewMode === "bed" ? part.bed_stl_b64 : part.design_stl_b64;

  const geometry = useMemo(() => decodeStlB64(b64), [b64]);

  useEffect(() => {
    return () => {
      if (geometry) geometry.dispose();
    };
  }, [geometry]);

  const target = useMemo(() => {
    if (viewMode === "bed") return [0, 0, 0];
    const [dx, dy, dz] = part.explode_vec || [0, 0, 0];
    return [dx * explode, dy * explode, dz * explode];
  }, [viewMode, explode, part.explode_vec]);

  useFrame((_, delta) => {
    if (!meshRef.current) return;
    const k = Math.min(1, delta * 14);
    meshRef.current.position.x = THREE.MathUtils.lerp(meshRef.current.position.x, target[0], k);
    meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, target[1], k);
    meshRef.current.position.z = THREE.MathUtils.lerp(meshRef.current.position.z, target[2], k);
  });

  if (!geometry || !visible) return null;

  const isTpu = part.group === "frame";

  return (
    <mesh ref={meshRef} geometry={geometry} castShadow receiveShadow>
      <meshStandardMaterial
        color={color}
        roughness={isTpu ? 0.58 : 0.34}
        metalness={isTpu ? 0.04 : 0.08}
      />
    </mesh>
  );
}

function PhoneGhostMesh({ b64, visible }) {
  const geometry = useMemo(() => decodeStlB64(b64), [b64]);
  useEffect(() => {
    return () => {
      if (geometry) geometry.dispose();
    };
  }, [geometry]);

  if (!geometry || !visible) return null;
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color="#94a3b8"
        transparent
        opacity={0.22}
        roughness={0.2}
        metalness={0.5}
        depthWrite={false}
      />
    </mesh>
  );
}

// The selected printer's plate (from the preview response), centred on the origin exactly as the
// server centres the Case_Set.3mf layout. A red plate means the parts do not fit (export blocked).
function BuildPlate({ x = 256, y = 256, fits = true }) {
  return (
    <group position={[0, 0, 0]}>
      <mesh position={[0, 0, -0.35]} receiveShadow>
        <boxGeometry args={[x, y, 0.7]} />
        <meshStandardMaterial color={fits ? "#18202c" : "#3b1219"} roughness={0.85} metalness={0.1} />
      </mesh>
      {/* 16 mm XY grid at Z=0, stretched to the plate's aspect ratio */}
      <gridHelper
        args={[x, Math.max(1, Math.round(x / 16)), fits ? "#38bdf8" : "#f43f5e", "#263345"]}
        scale={[1, 1, y / x]}
        rotation={[Math.PI / 2, 0, 0]}
        position={[0, 0, 0.02]}
      />
    </group>
  );
}

function AssemblyFloor() {
  return (
    <gridHelper
      args={[320, 32, "#1e293b", "#0f172a"]}
      rotation={[Math.PI / 2, 0, 0]}
      position={[0, 0, -68]}
    />
  );
}

export default function Viewport3D({
  preview,
  viewMode,
  explode,
  colors,
  visibleGroups,
  showPhoneGhost,
  bed,
  hideHud = false,
}) {
  const parts = preview?.parts || [];
  const phoneB64 = preview?.summary?.phone_stl_b64;

  return (
    <div className="relative h-full w-full bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{
          up: [0, 0, 1],
          position: viewMode === "bed" ? [0, -230, 220] : [135, -175, 115],
          fov: 36,
          near: 1,
          far: 3000,
        }}
      >
        <color attach="background" args={["#090d16"]} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[120, -140, 220]} intensity={1.35} castShadow shadow-mapSize={[1024, 1024]} />
        <directionalLight position={[-140, 120, 110]} intensity={0.65} color="#cbd5e1" />
        <directionalLight position={[0, 40, -160]} intensity={0.55} color="#7dd3fc" />

        <Environment resolution={64}>
          <Lightformer intensity={1.4} position={[0, -100, 160]} scale={[120, 120, 1]} color="#ffffff" />
          <Lightformer intensity={0.9} position={[140, 80, 60]} scale={[80, 120, 1]} color="#e0f2fe" />
          <Lightformer intensity={0.7} position={[-140, 60, -80]} scale={[100, 100, 1]} color="#cbd5e1" />
        </Environment>

        <group>
          {parts.map((part) => (
            <PartMesh
              key={part.id}
              part={part}
              viewMode={viewMode}
              explode={explode}
              color={colors[part.group] || "#94a3b8"}
              visible={visibleGroups[part.group] !== false}
            />
          ))}
          {viewMode === "assembly" && (
            <PhoneGhostMesh b64={phoneB64} visible={showPhoneGhost} />
          )}
        </group>

        {viewMode === "bed" ? <BuildPlate x={bed?.x} y={bed?.y} fits={bed?.fits !== false} /> : <AssemblyFloor />}

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          target={[0, 0, viewMode === "bed" ? 4 : 0]}
          minDistance={60}
          maxDistance={600}
        />
      </Canvas>

      {/* HUD Badges (optional when parent App renders unified HUD) */}
      {!hideHud && (
        <>
          <div className="pointer-events-none absolute top-3 left-3 flex flex-wrap gap-2">
            {viewMode === "bed" ? (
              <span className="rounded-md border border-cyan-500/40 bg-slate-950/85 px-2.5 py-1 text-xs font-medium text-cyan-300 backdrop-blur">
                {bed?.x ?? 256}×{bed?.y ?? 256} mm Build Plate (Z=0) · Pre-Oriented Back-Down
              </span>
            ) : (
              <span className="rounded-md border border-slate-700/70 bg-slate-950/85 px-2.5 py-1 text-xs font-medium text-slate-300 backdrop-blur">
                3D Assembly View · Explode {Math.round(explode * 100)}%
              </span>
            )}
            {preview?.summary && (
              <span className="rounded-md border border-slate-800 bg-slate-950/80 px-2.5 py-1 text-xs text-slate-400 backdrop-blur">
                Outer: {preview.summary.outer_width} × {preview.summary.outer_length} × {preview.summary.total_height} mm
              </span>
            )}
          </div>

          <div className="pointer-events-none absolute bottom-3 left-3 right-3 flex items-center justify-between text-[11px] text-slate-400">
            <span className="rounded bg-slate-950/75 px-2 py-1 border border-slate-800/80">
              Drag: Orbit · Right-Drag: Pan · Scroll: Zoom
            </span>
            {preview?.timings && (
              <span className="rounded bg-slate-950/75 px-2 py-1 border border-slate-800/80 font-mono text-[10px] text-slate-400">
                OCCT B-Rep: frame {preview.timings.frame}s · plate {preview.timings.backplate}s · ring {preview.timings.camera_ring}s · btns {preview.timings.buttons}s
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
