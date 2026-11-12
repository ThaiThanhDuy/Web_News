export type Sentiment = "positive" | "neutral" | "negative";

export interface Source {
  id: number;
  slug: string;
  name: string;
  homepage_url: string;
  logo_url: string;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
}

export interface Article {
  id: number;
  title: string;
  original_url: string;
  thumbnail_url: string | null;
  published_at: string;
  source: Source;
  category: Category | null;
  /** Other topics the story also belongs to (it's listed under them too). */
  related_categories?: Category[];
  summary_bullets: string[] | null;
  one_line_takeaway: string | null;
  keywords: string[] | null;
  sentiment: Sentiment | null;
  hotness_score: number;
  cross_source_count: number;
  /** One of the hottest stories leading a feed (sort=feed). */
  is_featured?: boolean;
  /** Featured partly because it matches the reader's interests. */
  is_personalized?: boolean;
}

export interface ArticlePage {
  items: Article[];
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
}
