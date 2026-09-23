-- Step 10h: the 15 videos_scored indexes dropped as unused, saved so each can be
-- recreated with one statement. video_id_idx is not here -- it was never dropped.
-- Generated 2026-09-23T16:04:36.629768

CREATE INDEX videos_scored_fts_idx ON public.videos_scored USING gin (fts);
CREATE INDEX videos_scored_cat_short_views_idx ON public.videos_scored USING btree (category, is_short, views DESC NULLS LAST);
CREATE INDEX videos_scored_cat_short_comments_idx ON public.videos_scored USING btree (category, is_short, comments DESC NULLS LAST);
CREATE INDEX videos_scored_cat_short_score_views_idx ON public.videos_scored USING btree (category, is_short, score_views DESC NULLS LAST);
CREATE INDEX videos_scored_cat_short_score_comments_idx ON public.videos_scored USING btree (category, is_short, score_comments DESC NULLS LAST);
CREATE INDEX videos_scored_cat_short_likes_idx ON public.videos_scored USING btree (category, is_short, likes DESC NULLS LAST);
CREATE INDEX videos_scored_cat_short_score_likes_idx ON public.videos_scored USING btree (category, is_short, score_likes DESC NULLS LAST);
CREATE INDEX videos_scored_published_at_idx ON public.videos_scored USING btree (published_at);
CREATE INDEX videos_scored_is_short_idx ON public.videos_scored USING btree (is_short);
CREATE INDEX videos_scored_short_views_idx ON public.videos_scored USING btree (is_short, views DESC NULLS LAST);
CREATE INDEX videos_scored_short_likes_idx ON public.videos_scored USING btree (is_short, likes DESC NULLS LAST);
CREATE INDEX videos_scored_short_comments_idx ON public.videos_scored USING btree (is_short, comments DESC NULLS LAST);
CREATE INDEX videos_scored_short_score_likes_idx ON public.videos_scored USING btree (is_short, score_likes DESC NULLS LAST);
CREATE INDEX videos_scored_short_score_comments_idx ON public.videos_scored USING btree (is_short, score_comments DESC NULLS LAST);
CREATE INDEX videos_scored_short_score_views_idx ON public.videos_scored USING btree (is_short, score_views DESC NULLS LAST);
