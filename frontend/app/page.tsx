import { SatelliteDish } from "lucide-react";

import { Feed } from "@/components/feed";
import { getArticles } from "@/lib/api";

const PAGE_SIZE = 10;

export default async function HomePage() {
  const feedPage = await getArticles({ sort: "feed", page: 1, pageSize: PAGE_SIZE });

  return (
    <div className="space-y-6">
      {feedPage.items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border py-24 text-center text-muted-foreground">
          <SatelliteDish className="h-8 w-8 text-muted-foreground/50" />
          <p className="font-semibold text-foreground">Chưa có tin nào được xử lý.</p>
          <p className="max-w-sm text-sm">
            Hãy chắc chắn backend, Postgres, Redis và Celery worker/beat đang chạy để hệ thống bắt
            đầu cào và tóm tắt tin.
          </p>
        </div>
      ) : (
        <div className="mx-auto max-w-2xl">
          <Feed initialItems={feedPage.items} initialPage={1} pageSize={PAGE_SIZE} initialHasMore={feedPage.has_more} />
        </div>
      )}
    </div>
  );
}
