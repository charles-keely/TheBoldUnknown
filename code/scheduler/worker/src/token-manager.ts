/**
 * Token Manager - Handles Instagram access token refresh
 */

import type { Env, TokenRefreshResult } from './types';
import { getActiveToken, saveNewToken, updateTokenLastUsed } from './db';

/**
 * Exchange a token for a long-lived token via Meta Graph API
 */
async function exchangeForLongLivedToken(
  env: Env,
  currentToken: string
): Promise<TokenRefreshResult> {
  const url = new URL(`https://graph.facebook.com/${env.GRAPH_API_VERSION}/oauth/access_token`);
  url.searchParams.set('grant_type', 'fb_exchange_token');
  url.searchParams.set('client_id', env.META_APP_ID);
  url.searchParams.set('client_secret', env.META_APP_SECRET);
  url.searchParams.set('fb_exchange_token', currentToken);
  
  try {
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Token exchange failed:', response.status, errorText);
      return {
        success: false,
        error: `Token exchange failed: ${response.status} - ${errorText.slice(0, 200)}`,
      };
    }
    
    const data = await response.json() as {
      access_token?: string;
      token_type?: string;
      expires_in?: number;
    };
    
    if (!data.access_token) {
      return {
        success: false,
        error: 'No access_token in response',
      };
    }
    
    // Calculate expiry (expires_in is in seconds)
    const expiresIn = data.expires_in || 5184000; // Default 60 days
    const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();
    
    return {
      success: true,
      access_token: data.access_token,
      expires_at: expiresAt,
    };
  } catch (error) {
    console.error('Token exchange error:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * Check if token needs refresh and refresh if necessary
 */
export async function ensureFreshToken(env: Env): Promise<string | null> {
  const token = await getActiveToken(env);
  
  if (!token) {
    console.error('No active Instagram token found');
    return null;
  }
  
  // Check if refresh is needed
  const refreshWindowDays = parseInt(env.TOKEN_REFRESH_WINDOW_DAYS || '7', 10);
  const expiresAt = new Date(token.expires_at);
  const now = new Date();
  const daysUntilExpiry = (expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  
  console.log(`Token expires in ${daysUntilExpiry.toFixed(1)} days`);
  
  if (daysUntilExpiry <= refreshWindowDays) {
    console.log(`Token expires within ${refreshWindowDays} days, refreshing...`);
    
    // Check if we have app credentials
    if (!env.META_APP_ID || !env.META_APP_SECRET) {
      console.error('Cannot refresh token: META_APP_ID and META_APP_SECRET are required');
      // Return the current token anyway, it might still work
      return token.access_token;
    }
    
    const result = await exchangeForLongLivedToken(env, token.access_token);
    
    if (result.success && result.access_token && result.expires_at) {
      // Save the new token
      const saved = await saveNewToken(env, result.access_token, result.expires_at);
      
      if (saved) {
        console.log(`Token refreshed successfully, new expiry: ${result.expires_at}`);
        return result.access_token;
      } else {
        console.error('Failed to save refreshed token');
        return token.access_token;  // Return old token as fallback
      }
    } else {
      console.error('Token refresh failed:', result.error);
      // Return the current token anyway, it might still work
      return token.access_token;
    }
  }
  
  // Update last used timestamp
  await updateTokenLastUsed(env, token.id);
  
  return token.access_token;
}

/**
 * Validate that a token can access the Instagram user
 */
export async function validateToken(env: Env, accessToken: string): Promise<boolean> {
  const url = `https://graph.facebook.com/${env.GRAPH_API_VERSION}/${env.IG_USER_ID}?fields=id&access_token=${accessToken}`;
  
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Token validation failed:', response.status, errorText);
      return false;
    }
    
    const data = await response.json() as { id?: string };
    return data.id === env.IG_USER_ID;
  } catch (error) {
    console.error('Token validation error:', error);
    return false;
  }
}


