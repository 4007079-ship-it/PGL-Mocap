#include "PGLMocapLiveLinkSource.h"

#include "ILiveLinkClient.h"
#include "Roles/LiveLinkAnimationRole.h"
#include "Roles/LiveLinkAnimationTypes.h"
#include "Roles/LiveLinkBasicRole.h"
#include "Roles/LiveLinkTransformRole.h"
#include "Roles/LiveLinkTransformTypes.h"

#include "Common/UdpSocketBuilder.h"
#include "HAL/PlatformProcess.h"
#include "HAL/RunnableThread.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Containers/StringConv.h"

#define LOCTEXT_NAMESPACE "PGLMocapLiveLinkSource"

namespace PGLMocap
{
	static constexpr int32 RecvBufferSize = 256 * 1024;

	static bool ReadVector(const TArray<TSharedPtr<FJsonValue>>& Arr, int32 Offset, FVector& Out)
	{
		if (Arr.Num() < Offset + 3) { return false; }
		Out = FVector(Arr[Offset]->AsNumber(), Arr[Offset + 1]->AsNumber(), Arr[Offset + 2]->AsNumber());
		return true;
	}
}

FPGLMocapLiveLinkSource::FPGLMocapLiveLinkSource(int32 InPort)
	: Port(InPort)
{
	RecvBuffer.SetNumUninitialized(PGLMocap::RecvBufferSize);

	Socket = FUdpSocketBuilder(TEXT("PGLMocapLiveLink"))
		.AsNonBlocking()
		.AsReusable()
		.BoundToAddress(FIPv4Address::Any)
		.BoundToPort(Port)
		.WithReceiveBufferSize(2 * 1024 * 1024)
		.Build();

	if (Socket != nullptr)
	{
		SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
		Thread = FRunnableThread::Create(this, TEXT("PGLMocapLiveLinkReceiver"), 128 * 1024, TPri_AboveNormal);
	}
}

FPGLMocapLiveLinkSource::~FPGLMocapLiveLinkSource()
{
	Stop();
	if (Thread != nullptr)
	{
		Thread->WaitForCompletion();
		delete Thread;
		Thread = nullptr;
	}
	if (Socket != nullptr)
	{
		Socket->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket);
		Socket = nullptr;
	}
}

void FPGLMocapLiveLinkSource::ReceiveClient(ILiveLinkClient* InClient, FGuid InSourceGuid)
{
	SourceGuid = InSourceGuid;
	Client.store(InClient);   // after the guid: the receiver thread starts pushing once Client is set
}

bool FPGLMocapLiveLinkSource::IsSourceStillValid() const
{
	return !bStopping && Thread != nullptr && Socket != nullptr;
}

bool FPGLMocapLiveLinkSource::RequestSourceShutdown()
{
	Stop();
	return true;
}

FText FPGLMocapLiveLinkSource::GetSourceType() const
{
	return LOCTEXT("SourceType", "PGL Mocap");
}

FText FPGLMocapLiveLinkSource::GetSourceMachineName() const
{
	FScopeLock Lock(&StatusLock);
	return LastSender.IsEmpty()
		? FText::Format(LOCTEXT("MachineNoData", "UDP :{0}"), FText::AsNumber(Port, &FNumberFormattingOptions::DefaultNoGrouping()))
		: FText::FromString(LastSender);
}

FText FPGLMocapLiveLinkSource::GetSourceStatus() const
{
	if (Socket == nullptr)
	{
		return FText::Format(LOCTEXT("StatusPortBusy", "Port {0} is busy"), FText::AsNumber(Port, &FNumberFormattingOptions::DefaultNoGrouping()));
	}
	FScopeLock Lock(&StatusLock);
	if (LastPacketTime <= 0.0)
	{
		return LOCTEXT("StatusWaiting", "Waiting for PGL Mocap...");
	}
	if (FPlatformTime::Seconds() - LastPacketTime > 2.0)
	{
		return LOCTEXT("StatusNoData", "No data");
	}
	return FText::Format(LOCTEXT("StatusReceiving", "Receiving, persons: {0}"), FText::AsNumber(LastPersons));
}

void FPGLMocapLiveLinkSource::Stop()
{
	bStopping = true;
}

uint32 FPGLMocapLiveLinkSource::Run()
{
	TSharedRef<FInternetAddr> Sender = SocketSubsystem->CreateInternetAddr();

	while (!bStopping)
	{
		if (!Socket->Wait(ESocketWaitConditions::WaitForRead, FTimespan::FromMilliseconds(100)))
		{
			continue;
		}
		uint32 Pending = 0;
		while (!bStopping && Socket->HasPendingData(Pending))
		{
			int32 Read = 0;
			if (!Socket->RecvFrom(RecvBuffer.GetData(), RecvBuffer.Num(), Read, *Sender) || Read <= 0)
			{
				break;
			}
			{
				FScopeLock Lock(&StatusLock);
				LastSender = Sender->ToString(false);
			}
			if (Client.load() != nullptr)
			{
				HandlePacket(RecvBuffer.GetData(), Read);
			}
		}
	}
	return 0;
}

void FPGLMocapLiveLinkSource::HandlePacket(const uint8* Data, int32 Size)
{
	FUTF8ToTCHAR Converted(reinterpret_cast<const UTF8CHAR*>(Data), Size);
	const FString JsonString(Converted.Length(), Converted.Get());

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(JsonString);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		return;
	}

	FString Prefix = TEXT("PGL");
	Root->TryGetStringField(TEXT("prefix"), Prefix);

	const TArray<TSharedPtr<FJsonValue>>* Persons = nullptr;
	int32 PersonCount = 0;
	if (Root->TryGetArrayField(TEXT("persons"), Persons))
	{
		for (const TSharedPtr<FJsonValue>& PersonValue : *Persons)
		{
			if (!PersonValue.IsValid())
			{
				continue;
			}
			const TSharedPtr<FJsonObject> Person = PersonValue->AsObject();
			if (Person.IsValid())
			{
				HandlePerson(Prefix, Person);
				++PersonCount;
			}
		}
	}

	const TArray<TSharedPtr<FJsonValue>>* Lost = nullptr;
	if (Root->TryGetArrayField(TEXT("lost"), Lost))
	{
		for (const TSharedPtr<FJsonValue>& Id : *Lost)
		{
			if (Id.IsValid())
			{
				RemovePerson(Prefix, static_cast<int32>(Id->AsNumber()));
			}
		}
	}

	FScopeLock Lock(&StatusLock);
	LastPacketTime = FPlatformTime::Seconds();
	LastPersons = PersonCount;
}

void FPGLMocapLiveLinkSource::HandlePerson(const FString& Prefix, const TSharedPtr<FJsonObject>& Person)
{
	ILiveLinkClient* LiveLinkClient = Client.load();
	int32 PersonId = 1;
	Person->TryGetNumberField(TEXT("id"), PersonId);
	const FString Base = FString::Printf(TEXT("%s_P%d"), *Prefix, PersonId);
	TArray<FName>& Owned = PersonSubjects.FindOrAdd(PersonId);

	FVector RootLocation = FVector::ZeroVector;
	const TArray<TSharedPtr<FJsonValue>>* RootArr = nullptr;
	if (Person->TryGetArrayField(TEXT("root"), RootArr))
	{
		PGLMocap::ReadVector(*RootArr, 0, RootLocation);
	}

	// ---------------------------------------------------------------- skeleton (Animation role)
	const TArray<TSharedPtr<FJsonValue>>* Names = nullptr;
	const TArray<TSharedPtr<FJsonValue>>* Parents = nullptr;
	const TArray<TSharedPtr<FJsonValue>>* Bones = nullptr;
	if (Person->TryGetArrayField(TEXT("names"), Names)
		&& Person->TryGetArrayField(TEXT("parents"), Parents)
		&& Person->TryGetArrayField(TEXT("bones"), Bones)
		&& Names->Num() == Parents->Num() && Names->Num() == Bones->Num() && Names->Num() > 0)
	{
		const FName SubjectName(*Base);
		const FLiveLinkSubjectKey Key(SourceGuid, SubjectName);

		TArray<FName> BoneNames;
		TArray<int32> BoneParents;
		BoneNames.Reserve(Names->Num());
		BoneParents.Reserve(Names->Num());
		for (int32 i = 0; i < Names->Num(); ++i)
		{
			BoneNames.Add(FName(*(*Names)[i]->AsString()));
			BoneParents.Add(static_cast<int32>((*Parents)[i]->AsNumber()));
		}

		const TArray<FName>* Known = SkeletonSubjects.Find(SubjectName);
		if (Known == nullptr || *Known != BoneNames)
		{
			FLiveLinkStaticDataStruct StaticDataStruct(FLiveLinkSkeletonStaticData::StaticStruct());
			FLiveLinkSkeletonStaticData& StaticData = *StaticDataStruct.Cast<FLiveLinkSkeletonStaticData>();
			StaticData.SetBoneNames(BoneNames);
			StaticData.SetBoneParents(BoneParents);
			LiveLinkClient->PushSubjectStaticData_AnyThread(Key, ULiveLinkAnimationRole::StaticClass(), MoveTemp(StaticDataStruct));
			SkeletonSubjects.Add(SubjectName, BoneNames);
			Owned.AddUnique(SubjectName);
		}

		FLiveLinkFrameDataStruct FrameDataStruct(FLiveLinkAnimationFrameData::StaticStruct());
		FLiveLinkAnimationFrameData& FrameData = *FrameDataStruct.Cast<FLiveLinkAnimationFrameData>();
		FrameData.Transforms.Reserve(Bones->Num());
		for (const TSharedPtr<FJsonValue>& BoneValue : *Bones)
		{
			const TArray<TSharedPtr<FJsonValue>>& B = BoneValue->AsArray();
			FTransform T = FTransform::Identity;
			if (B.Num() == 7)
			{
				const FVector Location(B[0]->AsNumber(), B[1]->AsNumber(), B[2]->AsNumber());
				FQuat Rotation(B[3]->AsNumber(), B[4]->AsNumber(), B[5]->AsNumber(), B[6]->AsNumber());
				Rotation.Normalize();
				T = FTransform(Rotation, Location, FVector::OneVector);
			}
			FrameData.Transforms.Add(T);
		}
		LiveLinkClient->PushSubjectFrameData_AnyThread(Key, MoveTemp(FrameDataStruct));
	}

	// ---------------------------------------------------------------- points (Transform role)
	const TSharedPtr<FJsonObject>* Points = nullptr;
	if (Person->TryGetObjectField(TEXT("points"), Points) && Points != nullptr && Points->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Points)->Values)
		{
			FVector P;
			if (!Pair.Value.IsValid() || !PGLMocap::ReadVector(Pair.Value->AsArray(), 0, P))
			{
				continue;
			}
			const FName SubjectName(*FString::Printf(TEXT("%s_%s"), *Base, *Pair.Key));
			const FLiveLinkSubjectKey Key(SourceGuid, SubjectName);
			if (!TransformSubjects.Contains(SubjectName))
			{
				FLiveLinkStaticDataStruct StaticDataStruct(FLiveLinkTransformStaticData::StaticStruct());
				LiveLinkClient->PushSubjectStaticData_AnyThread(Key, ULiveLinkTransformRole::StaticClass(), MoveTemp(StaticDataStruct));
				TransformSubjects.Add(SubjectName);
				Owned.AddUnique(SubjectName);
			}
			FLiveLinkFrameDataStruct FrameDataStruct(FLiveLinkTransformFrameData::StaticStruct());
			FLiveLinkTransformFrameData& FrameData = *FrameDataStruct.Cast<FLiveLinkTransformFrameData>();
			FrameData.Transform = FTransform(FQuat::Identity, RootLocation + P, FVector::OneVector);
			LiveLinkClient->PushSubjectFrameData_AnyThread(Key, MoveTemp(FrameDataStruct));
		}
	}

	HandleCurves(Base, Person, Owned);
}

void FPGLMocapLiveLinkSource::HandleCurves(const FString& Base, const TSharedPtr<FJsonObject>& Person, TArray<FName>& Owned)
{
	// ---------------------------------------------------------------- face (Basic role, ARKit curve names)
	const TSharedPtr<FJsonObject>* Curves = nullptr;
	if (!Person->TryGetObjectField(TEXT("curves"), Curves) || Curves == nullptr || !Curves->IsValid())
	{
		return;
	}
	ILiveLinkClient* LiveLinkClient = Client.load();

	TArray<FName> Names;
	TArray<float> Values;
	Names.Reserve((*Curves)->Values.Num());
	Values.Reserve((*Curves)->Values.Num());
	for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Curves)->Values)
	{
		if (!Pair.Value.IsValid())
		{
			continue;
		}
		Names.Add(FName(*Pair.Key));
		Values.Add(static_cast<float>(Pair.Value->AsNumber()));
	}
	if (Names.Num() == 0)
	{
		return;
	}

	const FName SubjectName(*FString::Printf(TEXT("%s_face"), *Base));
	const FLiveLinkSubjectKey Key(SourceGuid, SubjectName);
	const TArray<FName>* Known = CurveSubjects.Find(SubjectName);
	if (Known == nullptr || *Known != Names)
	{
		FLiveLinkStaticDataStruct StaticDataStruct(FLiveLinkBaseStaticData::StaticStruct());
		StaticDataStruct.Cast<FLiveLinkBaseStaticData>()->PropertyNames = Names;
		LiveLinkClient->PushSubjectStaticData_AnyThread(Key, ULiveLinkBasicRole::StaticClass(), MoveTemp(StaticDataStruct));
		CurveSubjects.Add(SubjectName, Names);
		Owned.AddUnique(SubjectName);
	}

	FLiveLinkFrameDataStruct FrameDataStruct(FLiveLinkBaseFrameData::StaticStruct());
	FrameDataStruct.Cast<FLiveLinkBaseFrameData>()->PropertyValues = MoveTemp(Values);
	LiveLinkClient->PushSubjectFrameData_AnyThread(Key, MoveTemp(FrameDataStruct));
}

void FPGLMocapLiveLinkSource::RemovePerson(const FString& Prefix, int32 PersonId)
{
	ILiveLinkClient* LiveLinkClient = Client.load();
	TArray<FName> Owned;
	if (!PersonSubjects.RemoveAndCopyValue(PersonId, Owned))
	{
		return;
	}
	for (const FName& SubjectName : Owned)
	{
		LiveLinkClient->RemoveSubject_AnyThread(FLiveLinkSubjectKey(SourceGuid, SubjectName));
		SkeletonSubjects.Remove(SubjectName);
		TransformSubjects.Remove(SubjectName);
		CurveSubjects.Remove(SubjectName);
	}
}

#undef LOCTEXT_NAMESPACE
