#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class SEditableTextBox;

/** Small panel in "Live Link -> + Source -> PGL Mocap": UDP port and the Add button. */
class SPGLMocapLiveLinkSourcePanel : public SCompoundWidget
{
public:
	DECLARE_DELEGATE_OneParam(FOnAddClicked, int32 /*Port*/);

	SLATE_BEGIN_ARGS(SPGLMocapLiveLinkSourcePanel) {}
		SLATE_EVENT(FOnAddClicked, OnAddClicked)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	FReply HandleAddClicked();

	TSharedPtr<SEditableTextBox> PortText;
	FOnAddClicked OnAddClicked;
};
