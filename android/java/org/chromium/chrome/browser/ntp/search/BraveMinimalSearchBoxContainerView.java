// Copyright (c) 2026 The Brave Authors. All rights reserved.
// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this file,
// You can obtain one at https://mozilla.org/MPL/2.0/.

package org.chromium.chrome.browser.ntp.search;

import android.content.Context;
import android.graphics.Color;
import android.util.AttributeSet;
import android.util.TypedValue;
import android.view.View;
import android.view.ViewGroup;

import org.chromium.build.annotations.NullMarked;

/** Keeps the NTP's native search box start area reserved for the approved lock glyph. */
@NullMarked
public class BraveMinimalSearchBoxContainerView extends SearchBoxContainerView {
    public BraveMinimalSearchBoxContainerView(Context context, AttributeSet attrs) {
        super(context, attrs);
    }

    @Override
    void updateStartIconVisibility(boolean visible) {
        // Chromium can toggle between a search-engine logo and a plus button. The minimal
        // address field uses its own static lock icon instead, so neither optional icon is shown.
        mDseIconView.setVisibility(View.GONE);
        mPlusButton.setVisibility(View.GONE);
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        // Chromium updates this inner view height from NTP customization preferences. Pin it
        // to the 54dp height of the approved Penpot address field instead.
        int targetHeight =
                Math.round(54f * getResources().getDisplayMetrics().density);
        ViewGroup.LayoutParams layoutParams = mSearchBoxView.getLayoutParams();
        if (layoutParams.height != targetHeight) {
            layoutParams.height = targetHeight;
            mSearchBoxView.setLayoutParams(layoutParams);
        }
        super.onMeasure(widthMeasureSpec, heightMeasureSpec);

        // Search-engine theme updates also reapply Chromium's default text appearance. Keep the
        // label readable on the pure-black surface while retaining the real edit/search behavior.
        float targetTextSize =
                TypedValue.applyDimension(
                        TypedValue.COMPLEX_UNIT_SP,
                        13f,
                        getResources().getDisplayMetrics());
        if (Math.abs(mHintTextView.getTextSize() - targetTextSize) > 0.5f) {
            mHintTextView.setTextSize(TypedValue.COMPLEX_UNIT_PX, targetTextSize);
        }
        if (mHintTextView.getCurrentTextColor() != Color.WHITE) {
            mHintTextView.setTextColor(Color.WHITE);
        }
        int hintColor = Color.rgb(154, 154, 154);
        if (mHintTextView.getHintTextColors().getDefaultColor() != hintColor) {
            mHintTextView.setHintTextColor(hintColor);
        }
    }
}
