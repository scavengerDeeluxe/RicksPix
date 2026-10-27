import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface Photo {
  id: string; title: string; description: string; category: string;
  subcategory: string | null; captured_at: string | null;
  season: string | null; camera_model: string | null;
  thumb_url: string; image_url: string;
  likes: number; quality_score: number | null;
}
interface PhotoResult { photos: Photo[]; total: number; }
interface CategoryResult { categories: { category: string; total: number }[]; }
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule],
  template: `
    <header class="topbar"><div class="brand"><span class="brand-mark">RP<span>·</span></span><span>RICK'S PIX</span></div>
      <nav><a href="#explore">Explore</a><a href="#story">The story</a></nav></header>
    <main>
      <section class="hero">
        <div class="eyebrow">A PHOTOGRAPHIC LEGACY · 2001—2018</div>
        <h1>A lifetime of <em>looking closer.</em></h1>
        <p>Landscapes, wildlife, quiet moments and unexpected discoveries — photographs worth sharing, and memories worth keeping.</p>
        <a class="action" href="#explore">Explore the collection <span aria-hidden="true">↗</span></a>
        <div class="hero-foot"><span>THE NORTH SHORE & BEYOND</span><span>CURATED WITH CARE</span></div>
      </section>
      <section id="explore" class="collection">
        <div class="section-top"><div><div class="eyebrow">THE ARCHIVE</div><h2>Explore Rick's photographs</h2></div><span class="count">{{ total() }} photographs</span></div>
        <div class="filters" role="group" aria-label="Filter by category">
          <button *ngFor="let cat of categories()" [class.selected]="category() === cat" (click)="chooseCategory(cat)">{{cat}}</button>
        </div>
        <div *ngIf="loading()" class="empty">Loading photographs…</div>
        <div *ngIf="!loading() && !photos().length" class="empty">
          <div class="empty-icon">✳</div><h3>The archive is taking shape.</h3>
          <p>Rick's first 1,000 photographs have been cataloged locally. Their public previews and descriptions will appear here after import.</p>
        </div>
        <div class="photo-grid" *ngIf="photos().length">
          <article class="photo" *ngFor="let photo of photos()">
            <button class="photo-open" (click)="open(photo)" [attr.aria-label]="'View '+photo.title">
              <img [src]="photo.thumb_url" [alt]="photo.description" loading="lazy">
            </button>
            <div class="photo-meta"><div><h3>{{photo.title}}</h3><p>{{photo.category}} <span *ngIf="photo.captured_at">· {{photo.captured_at | date:'yyyy'}}</span></p></div>
              <button class="like" (click)="like(photo)" [attr.aria-label]="'Like '+photo.title">♡ {{photo.likes}}</button></div>
          </article>
        </div>
        <div class="load-row" *ngIf="photos().length && photos().length < total()"><button (click)="loadMore()" [disabled]="loading()">Show more photographs</button></div>
      </section>
      <section id="story" class="story"><div class="eyebrow">BEHIND THE LENS</div><h2>Every photograph<br>has a story.</h2>
      <p>This archive was created to share Rick's photographs with anyone who might find joy in them. Images of the natural world, ordinary days, and remarkable details — preserved so they can continue to be discovered and appreciated.</p>
      <span class="story-note">IN MEMORY OF RICK · PHOTOGRAPHS 2001—2018</span></section>
    </main>
    <footer><div class="brand">RICK'S PIX</div><span>Made to be explored, shared, and remembered.</span><span>© {{year}}</span></footer>
    <div class="archive-disclaimer">This archive is cataloged with AI assistance. Not every photograph has been individually reviewed, and the collection continues to be refined and curated.</div>
    <div class="lightbox" *ngIf="selected() as p" role="dialog" aria-modal="true" [attr.aria-label]="p.title" (click)="close()">
      <button class="close" (click)="close(); $event.stopPropagation()" aria-label="Close">×</button>
      <div class="viewer" (click)="$event.stopPropagation()"><img [src]="p.image_url" [alt]="p.description">
        <div class="viewer-caption"><div><h3>{{p.title}}</h3><p>{{p.description}}</p><small>{{p.camera_model || 'Camera unknown'}} · {{p.season || 'Season unknown'}}</small></div>
          <button class="like" (click)="like(p)">♡ {{p.likes}}</button></div>
      </div>
    </div>
  `,
})
export class AppComponent implements OnInit {
  private http = inject(HttpClient);
  readonly photos = signal<Photo[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly category = signal('All');
  readonly selected = signal<Photo | null>(null);
  readonly categories = signal<string[]>(['All']);
  readonly year = new Date().getFullYear();
  ngOnInit(): void { this.loadCategories(); this.fetch(false); }
  private loadCategories(): void {
    this.http.get<CategoryResult>('/api/categories').subscribe({
      next: result => this.categories.set(['All', ...result.categories.map(x => x.category)]),
    });
  }
  chooseCategory(cat: string): void { this.category.set(cat); this.fetch(false); }
  loadMore(): void { this.fetch(true); }
  private fetch(append: boolean): void {
    this.loading.set(true);
    const offset = append ? this.photos().length : 0;
    const cat = this.category() === 'All' ? '' : '&category=' + encodeURIComponent(this.category());
    this.http.get<PhotoResult>('/api/photos?limit=24&offset=' + offset + cat).subscribe({
      next: result => { this.photos.set(append ? [...this.photos(), ...result.photos] : result.photos); this.total.set(result.total); this.loading.set(false); },
      error: () => { if (!append) this.photos.set([]); this.loading.set(false); }
    });
  }
  open(photo: Photo): void { this.selected.set(photo); document.body.style.overflow = 'hidden'; }
  close(): void { this.selected.set(null); document.body.style.overflow = ''; }
  like(photo: Photo): void {
    let visitor = localStorage.getItem('rickspix-visitor');
    if (!visitor) { visitor = crypto.randomUUID(); localStorage.setItem('rickspix-visitor', visitor); }
    this.http.post<{ likes: number }>('/api/photos/' + encodeURIComponent(photo.id) + '/like', { visitor }).subscribe({
      next: result => { this.photos.update(xs => xs.map(x => x.id === photo.id ? {...x,likes:result.likes} : x)); if (this.selected()?.id === photo.id) this.selected.set({...photo,likes:result.likes}); }
    });
  }
}
