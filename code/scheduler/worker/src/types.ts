/**
 * Type definitions for the Scheduler Worker
 */

export interface Env {
  // Supabase
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  
  // Instagram
  IG_USER_ID: string;
  GRAPH_API_VERSION: string;
  
  // Meta App (for token refresh)
  META_APP_ID: string;
  META_APP_SECRET: string;
  
  // Configuration
  TOKEN_REFRESH_WINDOW_DAYS: string;
  MAX_RETRY_COUNT: string;
  TIMEZONE: string;
}

export interface ScheduledPost {
  id: string;
  story_generation_id: string;
  assembly_id: string | null;
  scheduled_at: string;
  position: number;
  status: 'scheduled' | 'approved' | 'publishing' | 'published' | 'failed';
  approved_at: string | null;
  published_at: string | null;
  instagram_media_id: string | null;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface IGAccessToken {
  id: string;
  access_token: string;
  token_type: string;
  expires_at: string;
  obtained_at: string;
  last_used_at: string | null;
  refresh_count: number;
  is_active: boolean;
}

export interface StoryAssembly {
  id: string;
  story_generation_id: string;
  assembly_data: AssemblyData;
  status: string;
}

export interface AssemblyData {
  version: number;
  story_generation_id: string;
  selected_generation_id?: string;
  selected_thumbnail_id?: string;
  slides: AssemblySlide[];
  metadata?: {
    created_at: string;
    updated_at: string;
  };
}

export interface AssemblySlide {
  id: string;
  type: 'cover' | 'text' | 'photo';
  template: string;
  visible: boolean;
  content: {
    title?: string;
    subtitle?: string;
    thumbnail_url?: string;
    text?: string;
    image_url?: string;
    caption?: string;
    domain_tag?: string;
  };
}

export interface StoryGeneration {
  id: string;
  hook_title: string;
  subtitle: string;
  domain_tag: string;
  instagram_caption: string | null;
  hashtags: string[] | null;
}

export interface RenderedSlide {
  index: number;
  filename: string;
  public_url: string;
}

export interface PublishResult {
  success: boolean;
  media_id?: string;
  error?: string;
}

export interface TokenRefreshResult {
  success: boolean;
  access_token?: string;
  expires_at?: string;
  error?: string;
}

