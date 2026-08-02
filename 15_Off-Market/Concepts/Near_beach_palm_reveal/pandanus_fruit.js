/* pandanus_fruit.js — procedural pandanus fruit head, drawn in the deck's
 * engraved style at any size and any roll angle.
 *
 * Why procedural rather than a cut-out of the drawing: the fruit in the source
 * is only 46x50px, and it has to come to rest several times that size and ROLL
 * on the way. A raster sprite upscales to mush and shimmers when rotated. Here
 * the drupes are real spherical Voronoi cells whose polygons are computed once
 * in sphere space, so rotating genuinely rolls them over the surface.
 *
 * Style is matched against the fruit as it appears in palm_reveal_deck.mp4:
 * a light lit body with dark drupe faces and thick light grooves between them.
 */

// ---- procedural pandanus fruit head, engraved ----------------------------
// Sites on a Fibonacci sphere, each given a real spherical Voronoi cell so the
// drupes TILE (share seams) the way they do on the actual fruit. Cell polygons
// are computed once in sphere space; rotating just rotates those points, so the
// pattern is genuinely attached to the surface and rolls with it.

const V = {
  sub:(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]],
  add:(a,b)=>[a[0]+b[0],a[1]+b[1],a[2]+b[2]],
  mul:(a,s)=>[a[0]*s,a[1]*s,a[2]*s],
  dot:(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2],
  cross:(a,b)=>[a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]],
  norm:(a)=>{const l=Math.hypot(...a)||1;return [a[0]/l,a[1]/l,a[2]/l];},
};

function fibSites(n){
  const p=[], ga=Math.PI*(3-Math.sqrt(5));
  for(let i=0;i<n;i++){
    const y=1-((i+0.5)/n)*2, r=Math.sqrt(Math.max(0,1-y*y)), th=ga*i;
    // deterministic jitter — real drupes are not a perfect lattice
    const j = (k)=>{const v=Math.sin((i+1)*k)*43758.5453; return (v-Math.floor(v))-0.5;};
    const q = V.norm([Math.cos(th)*r + j(12.9898)*0.085,
                      y            + j(78.2330)*0.085,
                      Math.sin(th)*r + j(37.7191)*0.085]);
    p.push(q);
  }
  return p;
}

// clip a convex polygon (2D, tangent plane) by half-plane dot(n,x) <= d
function clip(poly, nx, ny, d){
  const out=[];
  for(let i=0;i<poly.length;i++){
    const a=poly[i], b=poly[(i+1)%poly.length];
    const da=nx*a[0]+ny*a[1]-d, db=nx*b[0]+ny*b[1]-d;
    if(da<=0) out.push(a);
    if((da<0&&db>0)||(da>0&&db<0)){
      const t=da/(da-db);
      out.push([a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t]);
    }
  }
  return out;
}

function buildCells(n){
  const sites = fibSites(n);
  const spacing = Math.sqrt(4*Math.PI/n);
  const cells = [];
  for(let i=0;i<sites.length;i++){
    const p = sites[i];
    // tangent basis at p
    const up = Math.abs(p[1])<0.9 ? [0,1,0] : [1,0,0];
    const u = V.norm(V.cross(up,p)), v = V.cross(p,u);
    // start with a generous hexagon in the tangent plane, then clip
    let poly=[]; const R0 = spacing*1.6;
    for(let k=0;k<8;k++){const a=(k/8)*Math.PI*2; poly.push([Math.cos(a)*R0, Math.sin(a)*R0]);}
    // clip against the perpendicular bisector of every nearby site
    const near = sites.map((q,j)=>({q,j,d:V.dot(p,q)}))
                      .filter(o=>o.j!==i && o.d>Math.cos(spacing*3))
                      .sort((a,b)=>b.d-a.d).slice(0,14);
    for(const {q} of near){
      const dq = V.sub(q,p);
      const qx = V.dot(dq,u), qy = V.dot(dq,v);
      const len = Math.hypot(qx,qy) || 1;
      poly = clip(poly, qx/len, qy/len, len/2);
      if(poly.length<3) break;
    }
    if(poly.length<3) continue;
    // shrink very slightly so a seam of background shows between drupes
    const cxl = poly.reduce((s,a)=>s+a[0],0)/poly.length;
    const cyl = poly.reduce((s,a)=>s+a[1],0)/poly.length;
    const verts = poly.map(([x,y])=>{
      const k = 0.60 + 0.10*Math.abs(Math.sin(i*3.3));   // vary drupe size
      const sx = cxl + (x-cxl)*k, sy = cyl + (y-cyl)*k;
      return V.norm(V.add(p, V.add(V.mul(u,sx), V.mul(v,sy))));
    });
    cells.push({c:p, verts});
  }
  return cells;
}

const CELLS = buildCells(132);

function rotX(p,a){const c=Math.cos(a),s=Math.sin(a);return [p[0], p[1]*c-p[2]*s, p[1]*s+p[2]*c];}
function rotZ(p,a){const c=Math.cos(a),s=Math.sin(a);return [p[0]*c-p[1]*s, p[0]*s+p[1]*c, p[2]];}

const LIGHT = V.norm([-0.5, 0.68, 0.55]);

function drawFruit(ctx, cx, cy, R, rot, lean, opt={}){
  const INK = opt.ink || "239,236,228";
  // Pandanus heads are ovoid — fuller at the base, tapering to the crown — not
  // spherical. Taper x/z by height so the silhouette reads as fruit, not ball.
  const squash = 1.10;
  const tf = (p)=>{
    const q = rotZ(rotX(p, rot), lean);
    const taper = 0.86 + 0.14*(1 - Math.max(0, q[1]));
    return [q[0]*taper, q[1]*squash, q[2]*taper];
  };

  const drawn = CELLS.map(cell=>({c:tf(cell.c), verts:cell.verts.map(tf)}))
                     .filter(o=>o.c[2] > -0.05)
                     .sort((a,b)=>a.c[2]-b.c[2]);

  // The lit surface first. In the drawing the grooves BETWEEN drupes are what
  // carries the light (they invert to bright in the dark theme), so the body is
  // painted light and the drupes are punched dark on top of it — the reverse of
  // outlining cells, which read as a wireframe.
  // Engraved shading, not a gradient. In the inverted (dark) theme the drawing's
  // dense hatch reads BRIGHT, so the strokes crowd where the surface turns away
  // from the light — the opposite of what it looks like it should be, but it is
  // what keeps the fruit in the same visual language as the tree.
  ctx.save();
  ctx.beginPath(); ctx.ellipse(cx, cy, R, R*squash, 0, 0, 7); ctx.clip();
  const ROWS = Math.max(14, Math.round(R * 0.42));
  ctx.lineCap = "round";
  for (let i = 0; i < ROWS; i++) {
    const t = (i + 0.5) / ROWS;            // 0 top -> 1 bottom of the body
    const yy = cy + (t * 2 - 1) * R * squash;
    const halfW = R * Math.sqrt(Math.max(0, 1 - Math.pow(t * 2 - 1, 2)));
    // surface normal at this latitude, roughly, for the light term
    const ny = -(t * 2 - 1);
    const shade = 1 - Math.max(0, (-0.42 * -0.6 + ny * 0.70 + 0.55 * 0.5));
    const dens = Math.pow(Math.max(0, Math.min(1, shade)), 1.15);
    if (dens < 0.06) continue;
    // Break each row into a couple of segments with gaps and a little jitter.
    // Full-width bands read as scan lines; a drawn hatch is never continuous.
    const bow = R * 0.16 * (t * 2 - 1);
    const segs = 1 + (i % 3);
    for (let sgi = 0; sgi < segs; sgi++) {
      const r0 = sgi / segs, r1 = (sgi + 1) / segs;
      const jitA = (Math.sin(i * 7.3 + sgi * 2.1) * 0.5 + 0.5) * 0.16;
      const jitB = (Math.sin(i * 3.1 + sgi * 5.7) * 0.5 + 0.5) * 0.16;
      const a = -halfW + halfW * 2 * (r0 + jitA * (r1 - r0));
      const bx = -halfW + halfW * 2 * (r1 - jitB * (r1 - r0));
      if (bx - a < R * 0.05) continue;
      const dy = Math.sin(i * 12.9 + sgi) * R * 0.008;
      ctx.beginPath();
      ctx.moveTo(cx + a, yy + dy);
      ctx.quadraticCurveTo(cx + (a + bx) / 2, yy + dy + bow * 0.5, cx + bx, yy + dy);
      ctx.lineWidth = Math.max(0.5, R * 0.016) * (0.5 + 0.8 * dens);
      ctx.strokeStyle = `rgba(${INK},${(0.12 + 0.74 * dens).toFixed(3)})`;
      ctx.stroke();
    }
  }
  ctx.restore();

  for(const {c, verts} of drawn){
    const lam = Math.max(0, V.dot(c, LIGHT));
    const fore = Math.max(0, c[2]);
    const face = Math.pow(lam, 0.9);
    ctx.beginPath();
    verts.forEach(([x,y],k)=>{
      const px = cx + x*R, py = cy - y*R;
      k ? ctx.lineTo(px,py) : ctx.moveTo(px,py);
    });
    ctx.closePath();
    // drupe face: dark, deeper in shadow, softening at the rim so the
    // silhouette stays drawn rather than cut
    const a = 0.90 - 0.30*face;
    ctx.fillStyle = `rgba(0,0,0,${(a*(0.35+0.65*Math.min(1,fore*2.2))).toFixed(3)})`;
    ctx.fill();
    // a faint light edge on each drupe: engraved grooves catch the light and
    // it stops the cells reading as flat vector holes
    ctx.lineWidth = Math.max(0.4, R*0.006);
    ctx.strokeStyle = `rgba(${INK},${(0.10 + 0.22*face*fore).toFixed(3)})`;
    ctx.stroke();
  }
}


// grain, so the body reads as engraved rather than airbrushed
let GRAIN = null;
function grainTile(){
  if (GRAIN) return GRAIN;
  const n = 96, c = document.createElement("canvas");
  c.width = c.height = n;
  const g = c.getContext("2d"), img = g.createImageData(n, n);
  let seed = 99991;
  for (let i = 0; i < n*n; i++) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const v = 90 + (seed % 165);
    img.data[i*4] = img.data[i*4+1] = img.data[i*4+2] = v;
    img.data[i*4+3] = 255;
  }
  g.putImageData(img, 0, 0);
  return (GRAIN = c);
}

// Public: draw the fruit centred at (cx,cy) with radius R.
//   rot  — roll angle in radians (about the horizontal axis)
//   lean — slight tilt, so it doesn't read as a perfect wheel
function paintFruit(ctx, cx, cy, R, rot, lean){
  ctx.save();
  drawFruit(ctx, cx, cy, R, rot, lean);
  // clip grain to the fruit body
  ctx.beginPath(); ctx.ellipse(cx, cy, R, R*1.10, 0, 0, 7); ctx.clip();
  ctx.globalAlpha = 0.13;
  ctx.globalCompositeOperation = "overlay";
  ctx.fillStyle = ctx.createPattern(grainTile(), "repeat");
  ctx.fillRect(cx-R, cy-R*1.2, R*2, R*2.4);
  ctx.restore();
}
if (typeof window !== "undefined") { window.paintFruit = paintFruit; }
