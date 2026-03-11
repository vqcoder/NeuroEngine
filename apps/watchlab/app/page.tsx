import Link from 'next/link';

export default function HomePage() {
  return (
    <main>
      <div className="panel stack" style={{ maxWidth: 720, margin: '0 auto' }}>
        <h1>watchlab</h1>
        <p>
          Build a video library, then run sequential studies with clear one-click handoff between
          videos.
        </p>
        <div className="row">
          <Link href="/upload" className="button-link" data-testid="go-upload-page-link">
            Open video library upload
          </Link>
          <Link href="/study/demo" className="button-link" data-testid="go-demo-study-link">
            Open demo study
          </Link>
        </div>
        <p className="muted">
          Tip: add multiple video URLs in <code>/upload</code>, start sequence from video 1, then
          use "Start next study" after each video ends.
        </p>
      </div>
    </main>
  );
}
