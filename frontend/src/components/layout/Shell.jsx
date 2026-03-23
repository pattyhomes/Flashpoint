export default function Shell({ left, map, right, bottom, status }) {
  return (
    <div className="shell">
      <aside className="shell__left">{left}</aside>
      <main className="shell__map">{map}</main>
      <aside className="shell__right">{right}</aside>
      <section className="shell__bottom">{bottom}</section>
      <footer className="shell__status">{status}</footer>
    </div>
  )
}
