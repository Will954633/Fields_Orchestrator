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
      const k = 0.72 + 0.10*Math.abs(Math.sin(i*3.3));   // vary drupe size
      const sx = cxl + (x-cxl)*k, sy = cyl + (y-cyl)*k;
      return V.norm(V.add(p, V.add(V.mul(u,sx), V.mul(v,sy))));
    });
    cells.push({c:p, verts});
  }
  return cells;
}

const CELLS = buildCells(138);

function rotX(p,a){const c=Math.cos(a),s=Math.sin(a);return [p[0], p[1]*c-p[2]*s, p[1]*s+p[2]*c];}
function rotZ(p,a){const c=Math.cos(a),s=Math.sin(a);return [p[0]*c-p[1]*s, p[0]*s+p[1]*c, p[2]];}

const LIGHT = V.norm([-0.5, 0.68, 0.55]);

function drawFruit(ctx, cx, cy, R, rot, lean, opt={}){
  const INK = opt.ink || "239,236,228";
  // A pandanus head is a rounded prolate — closer to a football than a ball —
  // and on the ground it rolls about its LONG axis, like a barrel, not end over
  // end. So the long axis lies horizontal, along the roll axis, and rotation is
  // about that same axis. Consequence worth knowing: the silhouette barely
  // changes while rolling and only the surface moves, which is exactly what a
  // rolling fruit looks like. Rotating a vertically-elongated body (the first
  // version) tumbled it over its points, which is what it is too fat to do.
  const LONG = 1.15, GIRTH = 0.95;
  const tf = (p)=>{
    const q = rotZ(rotX(p, rot), lean);       // spin about the horizontal long axis
    return [q[0]*LONG, q[1]*GIRTH, q[2]*GIRTH];
  };
  const squash = GIRTH / LONG;

  const drawn = CELLS.map(cell=>({c:tf(cell.c), verts:cell.verts.map(tf)}))
                     .filter(o=>o.c[2] > -0.05)
                     .sort((a,b)=>a.c[2]-b.c[2]);

  // The lit surface first. In the drawing the grooves BETWEEN drupes are what
  // carries the light (they invert to bright in the dark theme), so the body is
  // painted light and the drupes are punched dark on top of it — the reverse of
  // outlining cells, which read as a wireframe.
  // The body is built FROM the drupes, not painted behind them.
  //
  // A single smooth ellipse behind the cells gives a perfectly elliptical
  // silhouette, and that is the thing that made it read as a ball rather than a
  // pandanus head — a real one is a knobbly cluster whose drupes break the
  // outline. Filling an enlarged copy of every cell first builds the light
  // groove network AND a bumpy edge in one pass.
  for(const {c, verts} of drawn){
    const lam = Math.max(0, V.dot(c, LIGHT));
    const fore = Math.max(0, c[2]);
    const face = Math.pow(lam, 0.9);
    ctx.beginPath();
    verts.forEach(([vx,vy],k)=>{
      const px = cx + vx*R*1.055, py = cy - vy*R*1.055;
      k ? ctx.lineTo(px,py) : ctx.moveTo(px,py);
    });
    ctx.closePath();
    ctx.fillStyle = `rgba(${INK},${(0.13 + 0.60*face*(0.40+0.60*fore)).toFixed(3)})`;
    ctx.fill();
  }

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
    // Drupe face. Flat polygons read as vector cut-outs, so each face is filled
    // dark and then given its own short hatch strokes — the density of those
    // strokes is what carries the shading, the way it does in the drawing.
    const a = 0.94 - 0.20*face;
    ctx.fillStyle = `rgba(0,0,0,${(a*(0.35+0.65*Math.min(1,fore*2.2))).toFixed(3)})`;
    ctx.fill();

    // cell extent, for sizing the hatch inside it
    let x0=1e9, x1=-1e9, y0=1e9, y1=-1e9;
    for (const [vx,vy] of verts) {
      const px = cx + vx*R, py = cy - vy*R;
      if(px<x0)x0=px; if(px>x1)x1=px; if(py<y0)y0=py; if(py>y1)y1=py;
    }
    const cw = x1-x0, ch = y1-y0;

    // Only worth drawing once a drupe is big enough to read — below that the
    // strokes just turn to mud and cost frames. The fruit spends most of the
    // roll small, so this LOD matters.
    if (cw > 14 && fore > 0.30 && !(typeof window!=='undefined' && window.__NOHATCH)) {
      ctx.save();
      ctx.beginPath();
      verts.forEach(([vx,vy],k)=>{
        const px = cx + vx*R, py = cy - vy*R;
        k ? ctx.lineTo(px,py) : ctx.moveTo(px,py);
      });
      ctx.closePath(); ctx.clip();
      const lines = Math.max(2, Math.round(ch / Math.max(3.2, R*0.040)));
      ctx.lineCap = "round";
      // Each drupe hatches at its own angle. All-parallel hatch across
      // neighbouring cells reads as corduroy rather than as separate drupes.
      ctx.translate((x0+x1)/2, (y0+y1)/2);
      ctx.rotate((c[0]*1.9 + c[1]*2.7));
      ctx.translate(-(x0+x1)/2, -(y0+y1)/2);
      for (let li = 0; li < lines; li++) {
        const ly = y0 + (li + 0.5) / lines * ch;
        // hatch is denser away from the light, same inversion as the body
        const dens = 1 - face;
        if (((li * 7 + Math.round(c[0]*31)) % 5) / 5 > dens + 0.25) continue;
        const inset = cw * 0.06 * (0.5 + ((li*13)%7)/7);
        ctx.beginPath();
        ctx.moveTo(x0 + inset, ly);
        ctx.lineTo(x1 - inset, ly + (((li*11)%5)-2) * 0.25);
        ctx.lineWidth = Math.max(0.45, R*0.010);
        ctx.strokeStyle = `rgba(${INK},${(0.07 + 0.17*dens).toFixed(3)})`;
        ctx.stroke();
      }
      ctx.restore();
    }

    // Rebuild the cell path before outlining it. ctx.restore() restores the
    // transform, clip and styles but NOT the current path — so after the hatch
    // block the current path is the last hatch segment, and stroking it here
    // sprayed stray lines across the silhouette.
    ctx.beginPath();
    verts.forEach(([vx,vy],k)=>{
      const px = cx + vx*R, py = cy - vy*R;
      k ? ctx.lineTo(px,py) : ctx.moveTo(px,py);
    });
    ctx.closePath();

    // engraved groove around the drupe, weight varying with the light
    ctx.lineWidth = Math.max(0.4, R*0.009*(0.6+0.7*face));
    ctx.strokeStyle = `rgba(${INK},${(0.16 + 0.46*face*(0.4+0.6*fore)).toFixed(3)})`;
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
  ctx.beginPath(); ctx.ellipse(cx, cy, R*1.15, R*0.95, 0, 0, 7); ctx.clip();
  ctx.globalAlpha = 0.13;
  ctx.globalCompositeOperation = "overlay";
  ctx.fillStyle = ctx.createPattern(grainTile(), "repeat");
  ctx.fillRect(cx-R, cy-R*1.2, R*2, R*2.4);
  ctx.restore();
}
// ---- drawn sprite sheet -------------------------------------------------
// fruit_sprites.png is the real pen-and-ink fruit wrapped onto the sphere (see
// build_fruit_sprites.py). It is what should actually be shown; the procedural
// fruit above stays as the fallback for the moments before the sheet has
// loaded, so the animation never has a hole in it.
// baseR: the body occupies this fraction of the tile — the rest is headroom
// for drupes standing proud of the outline, so the draw size compensates.
const SPRITE = { img: null, frames: 24, tile: 200, cols: 6, baseR: 0.88, ready: false };
// Loaded on demand, not at parse. The sheet is ~0.9 MB and is not needed until
// the fruit detaches, which is several seconds after card 03 appears — there is
// no reason for a reader on card 02 to pay for it.
if (typeof window !== "undefined") {
  let started = false;
  window.__loadSprites = () => {
    if (started) return;
    started = true;
    const im = new Image();
    im.onload = () => { SPRITE.img = im; SPRITE.ready = true; };
    im.src = "fruit_sprites.png";
  };
}

function paintFruitSprite(ctx, cx, cy, R, rot) {
  const n = SPRITE.frames;
  // rot runs negative when rolling left; wrap into [0, n)
  let f = Math.round((-rot / (Math.PI * 2)) * n) % n;
  if (f < 0) f += n;
  const sx = (f % SPRITE.cols) * SPRITE.tile;
  const sy = Math.floor(f / SPRITE.cols) * SPRITE.tile;
  const k = 1 / SPRITE.baseR;
  const w = R * 2 * 1.15 * k, h = R * 2 * 0.95 * k;  // prolate, long axis horizontal
  ctx.drawImage(SPRITE.img, sx, sy, SPRITE.tile, SPRITE.tile,
                cx - w / 2, cy - h / 2, w, h);
}

if (typeof window !== "undefined") {
  window.paintFruit = (ctx, cx, cy, R, rot, lean) => {
    if (SPRITE.ready) return paintFruitSprite(ctx, cx, cy, R, rot);
    paintFruit(ctx, cx, cy, R, rot, lean);
  };
  window.drawFruit = drawFruit;
  window.__spriteReady = () => SPRITE.ready;
}
