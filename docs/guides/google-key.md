# Keys and tokens

<p class="lead">Make one Google Maps key for your pages and let it work only on your own addresses, and get a Mapillary token. Panoramax needs nothing.</p>

Two roadstyle windows use a Google Maps JavaScript API key:

| Window | Without a key | With a key |
|---|---|---|
| [Google Street View](street-view.md) | works: the Classic embed | adds **Linked**: the map marker walks with you |
| [Google 3D](google-3d.md) | not available | works |

The two windows use the same key and the same settings. A key is not enough. Google
also checks the billing of the project, the APIs that the key can use, and the web address of the page.

## Make the key

Do these steps in the [Google Cloud console](https://console.cloud.google.com/).

1. Select a project, or make a new project.
2. Open **Billing** and link a billing account to the project. Google needs billing also for the
   free monthly use.
3. Open **APIs & Services → Library**, find **Maps JavaScript API**, and click **Enable**. Do the same for **Maps Embed API** (it is used by Classic). These are
   the only APIs that roadstyle uses.
4. Open **APIs & Services → Credentials** and click **Create credentials → API key**.
5. Click the name of the new key to edit it.

## Limit the key to your addresses

Each page has the key in its HTML. Each person who opens the page can read the key. The
**Websites** list stops other sites from using your key.

1. Under **Application restrictions**, select **Websites**.
2. Under **Website restrictions**, add one line for each address where your pages run:

    | Your pages run on | Add this line |
    |---|---|
    | your computer, `python -m http.server 8000` | `http://localhost:8000/*` |
    | GitHub Pages, repository `maps` of user `name` | `https://name.github.io/maps/*` |
    | your own site | `https://www.example.com/*` |

3. Under **API restrictions**, select **Restrict key** and select **Maps JavaScript API** and **Maps Embed API**.
4. Click **Save**. Google can need up to 5 minutes before the new settings work.

!!! note "Each port is a different address"
    `http://localhost:8000/*` does not let the key work on `http://localhost:8001/`. Add one line for each port that you use.
    A page opened from disk (`file://`) has no address, so the key never works there. Serve the page.

## Give the key to roadstyle

Set the environment variable `GOOGLE_MAPS_KEY` before you make the pages. Each page that you
make has the key:

```bash
export GOOGLE_MAPS_KEY=AIza...
```

Or give the key to one page:

```python
rs.render_edges(edges, street_view_key=KEY)                   # Street View with Linked
rs.render_edges(edges, street_view_key=KEY, google_3d=True)   # and the Google 3D window
```

!!! warning "Publish only pages with a limited key"
    Before you put a page on a public site or in a public repository, make sure that its key has the
    Websites list above. A key with no limits lets other sites use your billing account.

## Costs

Google bills each Street View panorama and each Google 3D view above a free monthly quantity.
The two have different prices. See [Google Maps Platform pricing](https://mapsplatform.google.com/pricing/).
To get an email before the costs are high, open **Billing → Budgets & alerts** and make a budget.

## If the key does not work

Open the browser console (F12). Google writes the cause in it:

| Message in the console | Cause | Do this |
|---|---|---|
| `RefererNotAllowedMapError` | the address of the page is not in the Websites list | add the address (with its port), then wait 5 minutes |
| `ApiNotActivatedMapError` | the Maps JavaScript API is not enabled | enable it (step 3 of "Make the key") |
| `BillingNotEnabledMapError` | the project has no billing account | link a billing account (step 2) |
| `InvalidKeyMapError` | the key is not correct | copy the key again from **Credentials** |

The Google 3D window also shows "Google refused the key on this page" with the address to add.

## The Mapillary token

The Mapillary tab of the [Street View](street-view.md#panoramax-and-mapillary) window needs a free client token. Panoramax needs no key and no token.

1. Sign in at [mapillary.com/developer](https://www.mapillary.com/developer) and register an application.
2. Copy its *client token*.
3. On the page, open **Settings → Keys**, paste the token in *Mapillary token*, and click **Save**.
4. Click **Reload**.

The token stays in this browser. It is not in the page. Without a token, the Mapillary tab says that it needs one.

If you give a token with `mapillary_token=` or with the variable `MAPILLARY_TOKEN`, the page **has the token in it**. Everyone who opens the page can read it. Use a token that is limited to your site.

The same **Settings → Keys** box also takes the Google key, for a page that has none.

