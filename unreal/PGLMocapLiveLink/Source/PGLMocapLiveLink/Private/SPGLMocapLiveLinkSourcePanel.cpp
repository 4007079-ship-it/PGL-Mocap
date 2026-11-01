#include "SPGLMocapLiveLinkSourcePanel.h"

#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

#define LOCTEXT_NAMESPACE "PGLMocapLiveLinkSourcePanel"

void SPGLMocapLiveLinkSourcePanel::Construct(const FArguments& InArgs)
{
	OnAddClicked = InArgs._OnAddClicked;

	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(260.f)
		.Padding(FMargin(4.f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 2.f)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(0.5f)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(LOCTEXT("PortLabel", "UDP port"))
				]
				+ SHorizontalBox::Slot()
				.FillWidth(0.5f)
				[
					SAssignNew(PortText, SEditableTextBox)
					.Text(FText::FromString(TEXT("54321")))
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 2.f)
			[
				SNew(STextBlock)
				.AutoWrapText(true)
				.Text(LOCTEXT("Hint", "Use the same port as on the \"Unreal Live Link\" tab in PGL Mocap."))
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Right)
			.Padding(0.f, 4.f, 0.f, 0.f)
			[
				SNew(SButton)
				.OnClicked(this, &SPGLMocapLiveLinkSourcePanel::HandleAddClicked)
				[
					SNew(STextBlock)
					.Text(LOCTEXT("Add", "Add"))
				]
			]
		]
	];
}

FReply SPGLMocapLiveLinkSourcePanel::HandleAddClicked()
{
	int32 Port = 54321;
	if (PortText.IsValid())
	{
		LexFromString(Port, *PortText->GetText().ToString().TrimStartAndEnd());
	}
	if (Port <= 0 || Port > 65535)
	{
		Port = 54321;
	}
	OnAddClicked.ExecuteIfBound(Port);
	return FReply::Handled();
}

#undef LOCTEXT_NAMESPACE
